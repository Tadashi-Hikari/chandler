#   Copyright (c) 2003-2009 Open Source Applications Foundation
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.


import os, sys, threading, time, logging, cStringIO
import wx, Globals, Utility
from datetime import datetime

from new import classobj
from i18n import ChandlerMessageFactory as _, getImage, getLocaleSet
import schema, feedback
from version import version

from chandlerdb.persistence.RepositoryError import \
    RepositoryVersionError, RepositoryPlatformError, VersionConflictError
from chandlerdb.persistence.RepositoryView import otherViewWins



logger = logging.getLogger(__name__)

wxWindow_FindFocus = wx.Window_FindFocus

# SCHEMA_VERSION is now app_version in version.py

#@@@Temporary testing tool written by Morgen -- DJA
import util.timing

# Event used to post callbacks on the UI thread

wxEVT_MAIN_THREAD_CALLBACK = wx.NewEventType()
EVT_MAIN_THREAD_CALLBACK = wx.PyEventBinder(wxEVT_MAIN_THREAD_CALLBACK, 0)

def mixinAClass (self, myMixinClassImportPath):
    """
    Given an object, self, and the path as a string to a mixin class,
    myMixinClassImportPath, create a new subclass derived from base class
    of self and the mixin class and makes self's class this new class.

    This is useful to dynamicly (at runtime) mixin new behavior.
    """
    if not self.__class__.__dict__.get ("_alreadyMixedIn"):
        try:
            _classesByName = self.__class__._classesByName
        except AttributeError:
            self.__class__._classesByName = {}
            _classesByName = self.__class__._classesByName

        parts = myMixinClassImportPath.split (".")
        assert len(parts) >= 2, "Delegate %s isn't a module name plus a class name" % myMixinClassImportPath
        
        delegateClassName = parts.pop ()
        newClassName = delegateClassName + '_' + self.__class__.__name__
        try:
            theClass = _classesByName [newClassName]
        except KeyError:
            module = __import__ ('.'.join(parts), globals(), locals(), delegateClassName)
            assert module.__dict__.get (delegateClassName), "Class %s doesn't exist" % myMixinClassImportPath
            theClass = classobj (str(newClassName),
                                 (module.__dict__[delegateClassName], self.__class__,),
                                 {})
            theClass._alreadyMixedIn = True
            _classesByName [newClassName] = theClass
        self.__class__ = theClass

class MainThreadCallbackEvent(wx.PyEvent):
    def __init__(self, target, *args, **kwds):
        super (MainThreadCallbackEvent, self).__init__()
        self.SetEventType(wxEVT_MAIN_THREAD_CALLBACK)
        self.target = target
        self.args = args
        self.kwds = kwds
        self.lock = threading.Lock()

class wxBlockFrameWindow (wx.Frame):
    treeOfBlocks = None
    
    def __init__(self, *arguments, **keywords):
        super (wxBlockFrameWindow, self).__init__(*arguments, **keywords)

        self.SetBackgroundColour (wx.SystemSettings_GetColour(wx.SYS_COLOUR_3DFACE))
        self.Bind(wx.EVT_CLOSE, self.OnClose)
        self.Bind(wx.EVT_SIZE, self.OnSize)
        self.Bind(wx.EVT_MOVE, self.OnMove)
        self.app = wx.GetApp()

        self.icon = wx.Icon("Chandler.egg-info/resources/icons/Chandler_32.ico",
                            wx.BITMAP_TYPE_ICO)
        self.SetIcon(self.icon)

        if wx.Platform == "__WXMSW__":
            # if we're running on a Themed XP, and the display depth
            # gives us enough bits to play with, then this mode gives
            # us better looking toolbar icons, otherwise stick to the
            # default behavior.
            if wx.GetApp().GetComCtl32Version() >= 600 and wx.DisplayDepth() >= 32:
                wx.SystemOptions.SetOptionInt("msw.remap", 2)
            
        wx.SystemOptions.SetOption("mac.textcontrol-use-spell-checker", "1")
 
    def ShowTreeOfBlocks (self, treeOfBlocks):
        if self.treeOfBlocks:
            self.treeOfBlocks.unRender()
            self.SetSizer (None)

        self.treeOfBlocks = treeOfBlocks
        self.treeOfBlocks.frame = self
        self.treeOfBlocks.render()

        sizer = wx.BoxSizer (wx.HORIZONTAL)
        self.SetSizer (sizer)
        from osaf.framework.blocks.Block import wxRectangularChild
        sizer.Add (self.treeOfBlocks.widget,
                   self.treeOfBlocks.stretchFactor, 
                   wxRectangularChild.CalculateWXFlag(self.treeOfBlocks), 
                   wxRectangularChild.CalculateWXBorder(self.treeOfBlocks))
        sizer.Layout()

    def OnClose(self, event):
        if self.treeOfBlocks is not None:
            self.treeOfBlocks.unRender()
            self.SetSizer (None)
        event.Skip()

    def OnSize(self, event):
        # Calling Skip causes wxWindows to continue processing the event, 
        # which will cause the parent class to get a crack at the event.

        if not self.app.ignoreSynchronizeWidget:
            from osaf.pim.structs import SizeType
            # Our first child's block is the FrameWindow where we store size and position
            size = self.GetSize()
            children = self.GetChildren()
            if children:
                children[0].blockItem.size = SizeType (size.x, size.y)
        event.Skip()

    def OnMove(self, event):
        # Calling Skip causes wxWindows to continue processing the event, 
        # which will cause the parent class to get a crack at the event.
        
        if not self.app.ignoreSynchronizeWidget:
            from osaf.pim.structs import PositionType
            # Our first child's block is the FrameWindow where we store size and position
            position = self.GetPosition()
            self.GetChildren()[0].blockItem.position = PositionType(position.x, position.y)
        event.Skip()


class wxMainFrame (wxBlockFrameWindow):
    def __init__(self, *arguments, **keywords):
        super (wxMainFrame, self).__init__(*arguments, **keywords)

        # useful in debugging Mac background drawing problems
        #self.MacSetMetalAppearance(True)

        if wx.Platform == '__WXMAC__':
            # Fix for Bug 4156: On the Mac, when the app activates,
            # un-minimize the main window if necessary
            wx.GetApp().Bind(wx.EVT_ACTIVATE_APP, self.OnAppActivate)

    def OnAppActivate(self, event):
        # [Bug 12034] Only un-iconize if all app windows are iconized.
        if event.GetActive() and all(win.IsIconized()
                                         for win in wx.GetTopLevelWindows()):
                self.Iconize(False)

    def OnClose(self, event):
        """
        Main window is about to be closed when the application is quitting.
        Override of wxBlockFrameWindow.OnClose().
        """
        wx.GetApp().shutdown()


# We'll create a singleton item to remember our locale, to detect changes.
class LocaleInfo(schema.Item):
    localeName = schema.One(schema.Text)

class wxApplication (wx.App):
    # Class level flag that will
    # either be None or contain
    # a list of arguments to
    # pass when spawning a new
    # Chandler process.
    #
    # The population of this variable
    # with args tells the
    # OnExit method to spawn a
    # new Chandler process after the
    # current Repository instance
    # has been closed.
    #
    # The spawn code must be executed after
    # the Repository.close() method
    # to prevent two instances of
    # Chandler from accessing the
    # same Repository and is
    # a fix for bug [Bug 11186] File-Reload
    # throws RepositoryOpenDeniedError and
    # crashes app
    CHANDLER_RESTART_ARGS = None

    outputWindowClass = feedback.FeedbackWindow

    #List of callables for registering to be called during FilterEvent
    filterEventCallables = set()

    def FilterEvent (self, event):
        for callable in self.filterEventCallables:
            callable (event)
        return -1
    
    def OnInit(self):
        """
        Main application initialization.
        """
        self.initialized = False

        # Python errors caught by wx are emitted via PyErr_Print() which
        # outputs to Python's sys.stderr (bug 6586).
        #
        # Unless --stderr is used, ensure that all stderr output ends
        # up in the logger output.
        #
        # Unless --nocatch is used, Python's sys.stderr is already overriden
        # by the feedback window setup at this point.

        def ResizeAndRepositionInScreen (inputRect):
            """
            Set the inputRect to fit within the available screen. Returns the resized and
            repositioned rectangle (of type wx.Rect).
            """
            displayRect = wx.GetClientDisplayRect()
            
            assert inputRect.IsEmpty() is False
            assert displayRect.IsEmpty() is False
            
            # First, clip the width and height to the one of the display rectangle
            if displayRect.width < inputRect.width:
                inputRect.width = displayRect.width
            if displayRect.height < inputRect.height:
                inputRect.height = displayRect.height
                
            # Second, move the position so that the rectangle fits entirely in the display rectangle
            # This algorithm moves the position so that the window slides in by the minimum amount of
            # pixels. This is nice in situations like the Mac where the dock gets in the way but you 
            # don't want to reset the user chosen window position arbitrarily to the center or the 
            # origin of the screen. It's also nice for users switching from multiple screens to one
            # screen situations, the Chandler window simply sliding in instead of being reset to an
            # arbitrary default position.
            if inputRect.top < displayRect.top:
                inputRect.y += displayRect.top - inputRect.top
            if inputRect.bottom > displayRect.bottom:
                inputRect.y += displayRect.bottom - inputRect.bottom
            if inputRect.left < displayRect.left:
                inputRect.x += displayRect.left - inputRect.left
            if inputRect.right > displayRect.right:
                inputRect.x += displayRect.right - inputRect.right
            
            assert displayRect.ContainsRect(inputRect)
            return inputRect

        options = Globals.options

        if not options.stderr:

            class _stderr(object):
                def __init__(self, stderr):
                    self.stderr = stderr
                    self.output = []
                    self.logger = logging.getLogger('stderr')
                def __getattr__(self, name):
                    return getattr(self.stderr, name)
                def write(self, string):
                    self.stderr.write(string)
                    if string.endswith('\n'):
                        self.output.append(string.rstrip())
                        self.flush()
                    else:
                        self.output.append(string)
                def flush(self):
                    self.stderr.flush()
                    self.logger.warning(''.join(self.output))
                    self.output = []

            sys.stderr = _stderr(sys.stderr)


        # Ensure that all of wx's C/C++ stdout/stderr output goes to Python's
        # sys.stderr instead (bugs 6120, 6150)

        class _pyLog(wx.PyLog):
            def DoLogString(self, message, timestamp):

                if isinstance(message, unicode):
                    message = message.encode("utf-8", "replace")

                sys.stderr.write('wx output: ')
                sys.stderr.write(message)
                sys.stderr.write('\n')

        wx.Log.SetActiveTarget(_pyLog())

        self.startenv = os.environ.copy()

        # add plugin eggs and l10n eggs to working_set
        # collect plugin eggs
        pluginEnv, pluginEggs = Utility.initPluginEnv(options,
                                                      options.pluginPath)

        # The initI18n can't be initialized until after the App
        # object has been created since initialization creates a
        # wx.Locale object which requires a path that requires
        # GetTraits, which is a method on the App object.
        Utility.initI18n(options)

        util.timing.begin("wxApplication OnInit") #@@@Temporary testing tool written by Morgen -- DJA

        self.ignoreSynchronizeWidget = True
        self.focus = None

        # Check the Mac platform, will stop the program if not compatible
        if not checkMacPlatform():
            wx.MessageBox(_(u'This version of Chandler runs on a different operating system. Please download the correct installer from the OSAF website.'),
                          _(u'Quitting Chandler'))
            return False

        wx.InitAllImageHandlers()

        # Disable automatic calling of UpdateUIEvents. We will call them
        # manually when blocks get rendered, change visibility, etc.
        
        wx.UpdateUIEvent.SetUpdateInterval (-1)

        assert Globals.wxApplication is None, "We can have only one application"
        Globals.wxApplication = self
        self.updateUIInOnIdle = True
        
        # Initialize PARCELPATH and sys.path
        parcelPath = Utility.initParcelEnv(options, Globals.chandlerDirectory)

        # If a magic metakey is down, run the startup options box; it'll
        # modify options as necessary.
        if options.ask or wx.GetMouseState().ControlDown() \
            or (wx.Platform == '__WXMAC__' and wx.GetMouseState().AltDown()):
            from application.dialogs.StartupOptionsDialog import StartupOptionsDialog            
            StartupOptionsDialog.run()

        splashBitmap = self.GetImage("splash.png")
        splash = StartupSplash(None, splashBitmap)
        splash.Show()
        splash.Update()  # Force the window to refresh right now

        # Crypto initialization
        if splash:
            splash.updateGauge('crypto')
        Utility.initCrypto(options.profileDir)

        # repository initialization.
        if splash:
            splash.updateGauge('repository')

        try:
            view, repoDir, newRepo = Utility.openRepositoryOrBackup(self,
                                                                    options)
            if view is None:
                return True
        except RepositoryPlatformError, e:
            if self.ShowPlatformMismatchWindow(e.args[0], e.args[1]):
                options.create = True
                view = Utility.initRepository(repoDir, options)
            else:
                raise

        # check to see if we should do a time based auto-restore
        restorePrefs = schema.ns("osaf.app", view).autoRestorePrefs
        if (restorePrefs.enabled and restorePrefs.uptodateBackup and
              restorePrefs.hasLocalAttributeValue('nextRestore') and
              restorePrefs.nextRestore < datetime.now()):
            backup = os.path.join(options.profileDir, 'backup.chex')
            if os.path.isfile(backup):
                # Restore from backup, but first, just in case backup.chex fails,
                # make a binary backup
                Utility.stopRepository(view, commit=False)
                Utility.makeBinaryBackup(options)
                options.reload = backup
                options.create = True
                if splash:
                    splash.fixedMessage(_(u"Auto-restore from backup.chex..."))
                logger.info("Auto-restoring from backup.chex")
                view = Utility.initRepository(repoDir, options)
                restorePrefs = schema.ns("osaf.app", view).autoRestorePrefs

        restorePrefs.uptodateBackup = False

        self.repository = view.repository

        self.UIRepositoryView = view
        view.setMergeFn(otherViewWins)

        Utility.initOnlineStatus(view, options)

        # If the locale changed, force index rebuild. (We'll save the locale
        # below if it changed - we'll need the parcels loaded for that)
        if self.localeChanged():
            view.check(True)
        
        if splash:
            if options.reload is not None:
                splash.fixedMessage(_(u"Reloading collections and settings..."))
            elif (options.create or newRepo):
                splash.fixedMessage(_(u"Configuring data..."))

        # Bug 11818: Quick start guide when starting up Chandler for the
        #            first time
        # Only do this if it's a new repository (and also double-check that
        # we're not reloading, and that we're not in test mode).
        if newRepo and (options.reload is None) and (options.catch != 'tests'):
            wx.LaunchDefaultBrowser("http://chandlerproject.org/getstarted",
                                    wx.BROWSER_NEW_WINDOW)

        # Load Parcels
        if splash:
            splash.updateGauge('parcels')

        try:
            Utility.initParcels(options, view, parcelPath)
            Utility.initPlugins(options, view, pluginEnv, pluginEggs)
            Utility.initTimezone(options, view)
        except:
            if options.undo == 'start':
                logger.exception("Failed to start while initializing data, restarting and undoing latest version")
                self.restart(undo='start')
            else:
                raise

        # Now that the parcel world exists, save our locale for next time.
        self.saveLocale()
        
        self.Bind(wx.EVT_MENU, self.OnCommand, id=-1)
        self.Bind(wx.EVT_TOOL, self.OnCommand, id=-1)
        self.Bind(wx.EVT_UPDATE_UI, self.OnCommand, id=-1)
        self.Bind(wx.EVT_WINDOW_DESTROY, self.OnDestroyWindow, id=-1)
        self.Bind(wx.EVT_SHOW, self.OnShow, id=-1)
        self.Bind(wx.EVT_CONTEXT_MENU, self.OnContextMenu)

        # The Twisted Reactor should be started before other Managers
        # and stopped last.
        if splash:
            splash.updateGauge('twisted')
        Utility.initTwisted(view, options=options)

        # Start the reload before putting up the Chandler UI
        # (Bug 9533). For master password manipulation reasons,
        # it needs the twisted reactor to be running.
        if Globals.options.reload is not None:
            self.reload(splash)

        mainViewRoot = schema.ns("osaf.views.main", view).MainViewRoot

        # Fix for bug 3411: mainFrame gets resized when it is rendered
        # (particularly when the toolbar gets rendered), increasing the window's
        # height by the height of the toolbar.  We fix by remembering the
        # (correct) size before rendering and resizing. 
        rememberRect = wx.Rect(mainViewRoot.position.x, mainViewRoot.position.y,
                               mainViewRoot.size.width, mainViewRoot.size.height)

        self.mainFrame = wxMainFrame(None,
                                     -1,
                                     mainViewRoot.windowTitle,
                                     pos =( mainViewRoot.position.x, mainViewRoot.position.y),
                                     size =( mainViewRoot.size.width, mainViewRoot.size.height),
                                     style = wx.DEFAULT_FRAME_STYLE,
                                     name = mainViewRoot.blockName)

        # mainViewRoot needs to refer to its frame and the mainFrame needs to
        # refert to the mainViewRoot
        mainViewRoot.frame = self.mainFrame
        self.mainFrame.mainViewRoot = mainViewRoot

        # Register to some global events for name lookup.
        globalEvents = self.UIRepositoryView.findPath('//parcels/osaf/framework/blocks/GlobalEvents')

        from osaf.framework.blocks.Block import Block

        Block.addToNameToItemUUIDDictionary (globalEvents.eventsForNamedLookup,
                                             Block.eventNameToItemUUID)

        self.ignoreSynchronizeWidget = False

        if splash:
            splash.updateGauge('mainview')

        self.RenderMainView(splash)

        self.Yield(True)

        # Restore standalone detail view windows at launch
        # @@@ no call to updateGauge
        from osaf.views.detail import DetailFrameWindow
        
        for fw in DetailFrameWindow.iterItems(self.UIRepositoryView):
            fw.show()

        
        if splash:
            splash.updateGauge('commit')
        self.UIRepositoryView.commit()

        if splash:
            splash.updateGauge('services')
        # Start the WakeupCaller Service
        Utility.initWakeup(self.UIRepositoryView)

        # Start the Chandler Mail Service

        from osaf.mail.mailservice import MailService

        Globals.mailService = MailService(self.UIRepositoryView)
        Globals.mailService.startup()

        if splash:
            splash.Destroy()

        # delay calling OnIdle until now
        self.Bind(wx.EVT_IDLE, self.OnIdle)

        # reposition the window in the screen if needs be
        rememberRect = ResizeAndRepositionInScreen(rememberRect)

        # resize to the correct size
        self.mainFrame.SetRect(rememberRect)

        # Call UpdateWindowUI before we show the window. UPDATE_UI_FROMIDLE
        # should be set so we don't update menus, since they are done
        # when the menu is pulled down (mac may handle this slightly differently,
        # except we still want UPDATE_UI_FROMIDLE on mac) -- DJA
        self.mainFrame.UpdateWindowUI (wx.UPDATE_UI_FROMIDLE | wx.UPDATE_UI_RECURSE)
        self.needsUpdateUI = False

        self.mainFrame.Show()

        # Set focus so OnIdle won't trigger an unnecessary UpdateWindowUI the
        # first time through. -- DJA
        self.focus = wxWindow_FindFocus()


        # Register sharing activity to be sent to the status bar
        from osaf import sharing
        setStatusMessage = Block.findBlockByName('StatusBar').setStatusMessage
        def _setStatusMessageCallback(*args, **kwds):
            if kwds.get('msg', None) is not None:
                self.PostAsyncEvent(setStatusMessage, kwds['msg'])
        sharing.register(sharing.UPDATE, _setStatusMessageCallback)


        # To solve bug 8213 we need the main ui thread to examine new inbound
        # occurrence items to see if there are duplicate recurrenceIDs.  The
        # sharing layer will populate the newItems collection with occurrences
        # and this method pulls them out and inspects them.
        self.processSharingQueue = sharing.processSharingQueue


        # Register ourselves to be notified whenever there are unsubscribed
        # collections:
        from application.dialogs import RestoreShares
        sharing.register(sharing.UNSUBSCRIBEDCOLLECTIONS,
            RestoreShares.Show)


        # Fix for Bugs 3720, 3722, 5046, and 5650.  Sets the focus to
        # the first focusable widget in the frame, and also forces a
        # UpdateUI of the menus so the accelerator table will get built.
        if wx.Platform == '__WXGTK__':
            def afterInit():
                self.mainFrame.GetChildren()[0].SetFocus()
                self.mainFrame.UpdateWindowUI(wx.UPDATE_UI_RECURSE)
            wx.CallAfter(afterInit)


        # Start a background sync of shares, but only if not running tests,
        # and if the autosync function is not set to "manual" (indicated by
        # an autosync interval of None):
        if (Globals.options.catch != 'tests' and
            sharing.getAutoSyncInterval(self.UIRepositoryView) is not None):
            sharing.scheduleNow(self.UIRepositoryView)

        # Show "tip of the day"
        if Globals.options.catch not in ('tests', 'never'):
            def showTip():
                prefs = schema.ns("osaf.app",
                                  self.UIRepositoryView).prefs
                if prefs.showTip:
                    tp = wx.CreateFileTipProvider('application/tips.txt',
                                                  prefs.tipIndex)
                    prefs.showTip = wx.ShowTip(self.mainFrame, tp)
                    prefs.tipIndex = tp.GetCurrentTip()
            wx.CallAfter(showTip)

        util.timing.end("wxApplication OnInit") #@@@Temporary testing tool written by Morgen -- DJA

        self.initialized = True
        
        return True    # indicates we succeeded with initialization

    def reload(self, splash):
        from osaf.activity import Activity, ActivityAborted, Listener
        from osaf import dumpreload
        from osaf.framework.blocks.Block import Block

        def update(activity, *args, **kwds):
            # Can be called from any thread; will msg to main thread
            # if need be.
    
            if threading.currentThread().getName() != "MainThread":
                self.PostAsyncEvent(update, *args, **kwds)
            else:
                if 'msg' in kwds:
                    splash.fixedMessage(kwds['msg'])
                    self.Yield(True)

        activity = Activity(_(u"Reloading from %(path)s...") % {'path': unicode(Globals.options.reload, sys.getfilesystemencoding())})
        listener = Listener(activity=activity, callback=update)

        self.mainFrame = splash
        activity.started()

        # Don't show the timezone dialog during reload.
        tzprefs = schema.ns('osaf.pim', self.UIRepositoryView).TimezonePrefs
        oldShowPrompt = tzprefs.showPrompt
        tzprefs.showPrompt = False

        try:
            dumpreload.reload(self.UIRepositoryView, Globals.options.reload, 
                              activity=activity)
            activity.completed()
        except Exception, e:
            tzprefs.showPrompt = oldShowPrompt
            logger.exception("Failed to reload file")
            activity.failed(exception=e)
            if isinstance(e, TypeError):
                msg = _(u"Incompatible export file. Unable to reload. Restarting Chandler...")
            elif isinstance(e, EOFError):
                msg = _(u"Incomplete export file. Unable to reload. Restarting Chandler...")
            elif isinstance(e, ActivityAborted):
                msg = _(u"Reload cancelled. Restarting Chandler...")
            else:
                msg = _(u"Unable to reload file.  Go to the Tools>>Logging>>Log Window... menu for details. Chandler will now restart.")
            dialog = wx.MessageDialog(None, msg,
                     u"Chandler", wx.OK | wx.ICON_INFORMATION)
            dialog.ShowModal()
            dialog.Destroy()
            self.restart(create=True)
        
        def showStatus(msg):
            statusBar = Block.findBlockByName('StatusBar')
            if statusBar is not None:
                statusBar.setStatusMessage(msg)
        #L10N: The collections and settings that were exported to a dump file
        #      from a previous version of Chandler have now been reloaded
        #      in the latest version.
        self.PostAsyncEvent(showStatus, _(u'Collections and settings reloaded.'))

    def localeChanged(self):
        """
        See if the locale changed since the last time we ran Chandler.
        (Called at startup to see if we need to blow away any locale-sensitive
        repository indexes. Only checks once, then caches the result in a non-
        persistent attribute)
        """
        itChanged = getattr(self, '_localeChanged', None)
        if itChanged is not None:
            return itChanged
        
        localeInfo = self.UIRepositoryView.findPath('//parcels/localeInfo')
        if localeInfo is None:
            return False # we've never recorded a locale, so it can't have changed.
        
        import i18n
        itChanged = localeInfo.localeName != i18n.getLocale()
        self._localeChanged = itChanged
        return itChanged
    
    def saveLocale(self):
        """ Save our locale, if it changed or we hadn't saved it yet """
        # Don't bother saving unless it changed.
        if not getattr(self, '_localeChanged', True):
            return
        import i18n
        localeInfo = self.UIRepositoryView.findPath('//parcels/localeInfo')
        localeName = i18n.getLocale()
        if localeInfo is None:
            localeInfo = LocaleInfo.update(self.UIRepositoryView.getRoot('parcels'),
                                           'localeInfo',
                                           localeName=localeName)
        else:
            localeInfo.localeName = localeName
        
    def RenderMainView (self, splash=None):
        mainViewRoot = self.mainFrame.mainViewRoot
        mainViewRoot.render()

        if splash:
            splash.updateGauge("layout")

        # We have to wire up the block mainViewRoot, it's widget and sizer to a new
        # sizer that we add to the mainFrame.
        
        sizer = wx.BoxSizer (wx.HORIZONTAL)
        self.mainFrame.SetSizer (sizer)
        from osaf.framework.blocks.Block import wxRectangularChild
        sizer.Add (mainViewRoot.widget,
                   mainViewRoot.stretchFactor, 
                   wxRectangularChild.CalculateWXFlag(mainViewRoot), 
                   wxRectangularChild.CalculateWXBorder(mainViewRoot))
        sizer.Layout()
        # A bug in windows wxWidgets causes the toolbar synchronizeWidget to incorrectly
        # layout a the toolbar controls when it's called before the top level size is
        # layed out, so we'll ignore calls to wxSynchronizeLayout until the top level
        # sizer is installed
        from osaf.framework.blocks.Block import Block
        toolbar = Block.findBlockByName ("ApplicationBar")
        toolbar.synchronizeWidget()
        
        #allow callbacks from other threads
        EVT_MAIN_THREAD_CALLBACK(self, self.OnMainThreadCallbackEvent)


    def UnRenderMainView (self):
        #disable callbacks from other threads since they may depend on blocks
        #(i.e. the StatusBar being rendered
        EVT_MAIN_THREAD_CALLBACK(self, None)
        mainViewRoot = self.mainFrame.mainViewRoot.unRender()
        if __debug__:
            from osaf.framework.blocks.Block import Block
            view = self.UIRepositoryView
            for uWatched, watchers in view._watchers.iteritems():
                watchers = watchers.get(view.SUBSCRIBERS)
                if watchers:
                    for watcher in watchers:
                        item = view.findUUID(watcher.watchingItem)
                        assert not isinstance(item, Block)
            
        self.mainFrame.SetSizer (None)

    if __debug__:
        def PrintTree (self, widget, indent):
            sizer = widget.GetSizer()
            if sizer:
                for sizerItem in sizer.GetChildren():
                    if sizerItem.IsWindow():
                        window = sizerItem.GetWindow()
                        try:
                            name = window.blockItem.blockName
                        except AttributeError:
                            name = window.blockItem
                        print indent, name
                        self.PrintTree (window, indent + "  ")

    imageCache = {}

    def GetRawImage(self, name, copy=True):
        """
        Return None if image isn't found, otherwise return the raw image.
        Also look first for platform specific images.
        """
        entry = wxApplication.imageCache.get(name)
        if entry is not None:
            image = entry[0]
            if image is not None and copy:
                image = image.Copy()
            return image

        root, extension = os.path.splitext (name)

        file = getImage(root + "-" + sys.platform + extension)

        if file is None:
            file = getImage(name)

            if file is None:
                wxApplication.imageCache[name] = [None]
                return None

        image = wx.ImageFromStream(cStringIO.StringIO(file.read()))
        wxApplication.imageCache[name] = [image]
        if copy:
            image = image.Copy()
        return image

    def GetImage (self, name):
        """
        Return None if image isn't found, otherwise loads a bitmap.
        Looks first for platform specific bitmaps.
        """
        rawImage = self.GetRawImage(name, copy=False)

        if rawImage is not None:
            return wx.BitmapFromImage (rawImage)

        return None
    
    def OnCommand(self, event):
        """
        Catch commands and pass them along to the blocks.
        Our events have ids greater than wx.ID_HIGHEST
        Delay imports to avoid circular references.
        """
        import osaf.framework.blocks.Block as Block

        wxID = event.GetId()
        # Our goal here is to find the rendered block whose Id matches wxID.
        # In the case of our IDs, there's no problem, because they're unique.
        # For standard wx IDs (like wx.ID_COPY, for example) we need to make
        # sure we look in the correct top-level frame. To do this, we pass
        # in a non-None second argument to Block.findBlockById, which is used
        # as a hint to resolve which frame we want.
        
        # For menus, eventObject will be the frame the menu belongs to.
        eventObject = event.GetEventObject()
        # If the event has a blockItem, that is for sure the hint we want ...
        eventBlock = getattr(event, 'blockItem', None)
        # Otherwise, try the top-level block of a wxBlockFrameWindow, if
        # it exists.
        if eventBlock is None:
            eventBlock = getattr(eventObject, 'treeOfBlocks', None)
        block = Block.Block.findBlockById(wxID, eventBlock)
        if block is not None:
            isMacMenuEvent = (wx.Platform == '__WXMAC__' and
                              event.GetEventType() == wx.EVT_MENU.evtType[0])

            # Similar to below, when the Backspace key is used an as
            # accelerator on wxMac and the currently focused widget is
            # a textctrl then we *must* Skip the event otherwise the
            # text control will either do nothing, or will treat it as
            # a Delete key instead.
            if (isMacMenuEvent and
                getattr(block, 'accel', None) == "Back" and
                isinstance(wxWindow_FindFocus(), (wx.TextCtrl, wx.ComboBox))):
                event.Skip()
                return

            #An interesting problem occurs on Mac (see Bug #219). If a dialog is
            #the topmost windw, standard events like cut/copy/paste get processed
            #by this handler instead of the dialog, causing cut/copy/paste to stop
            #working in dialogs. So, instead, if the dialog handles the event we
            #don't want to dispatch it through our CPIA event mechanism.
            #
            #Unfortunately, it's not possible to know if the dialog can process
            #the event. So instead, when the dialog is frontmost, we'll only send
            #events belonging to blocks which have ids in the range we generate
            #with getWidgetID through our commands processing, otherwise we'll send
            #it to the dialog. This can be accomplished by not handling the event
            #here and, instead, calling Skip so it will be passed along to the dialog.
            #
            #Telling if a dialog is the topmost windows is also a bit tricky since
            #wx.GetActiveWindow is implemented only on windows, so wet get the top
            #level parent of whatever window has the focus
    
            if ((0 < wxID < wx.ID_LOWEST) or
                isinstance (wx.GetTopLevelParent(wxWindow_FindFocus()), wxBlockFrameWindow)):

                updateUIEvent = event.GetEventType() == wx.EVT_UPDATE_UI.evtType[0]
                blockEvent = getattr (block, 'event', None)
                # If a block doesn't have an event, it should be an updateUI event
                assert (blockEvent is not None or updateUIEvent)

                if blockEvent is not None:
                    arguments = {"wxEvent": event}
                    if updateUIEvent:
                        arguments ['UpdateUI'] = True
                    else:
                        if eventObject is not None:
                            method = getattr (eventObject, "GetToolState", None)
                            if method is not None:
                                arguments ['buttonState'] = method (wxID)

                    # skip further processing if we're propagating to a different
                    # top-level window. Maybe this should be done somewhere in
                    # the Block posting hierarchy -- grant
                    from osaf.framework.blocks import MenuItem
                    
                    if blockEvent.dispatchEnum == 'FocusBubbleUp':
                        focusBlock = Block.Block.getFocusBlock()
                        if (block.getRootBlock() is not focusBlock.getRootBlock()
                            and not (wx.Platform == '__WXMAC__'
                                    and isinstance(block, MenuItem))):
                            event.Skip()
                            return

                    Block.Block.post (blockEvent, arguments, block)

                    if updateUIEvent:
                        check = arguments.get ('Check', None)
                        if check is not None:
                            event.Check (check)
                        event.Enable (arguments.get ('Enable', True))

                        widget = getattr(block, 'widget', None)

                        text = arguments.get ('Text', None)
                        if text is not None and widget is not None:
                            event.SetText (text)
                            # menu items can get here, so check for toolbar item method
                            method = getattr (widget, "OnSetTextEvent", None)
                            if method is not None:
                                # Some widgets, e.g. wxToolBarItems don't properly handle
                                # setting the text of buttons, so we'll handle it here by
                                # calling OnSetTextEvent
                                method (event)

                        bitmap = arguments.get ('Bitmap', None)
                        if bitmap is not None and widget is not None:
                            # menu items can get here, so check for toolbar item method
                            method = getattr (widget, "SetToolBarItemBitmap", None)
                            if method is not None:
                                # The UI requires the bitmap to change; there is no SetBitmap()
                                # method for wx UpdateUIEvents, so just pass the name of the
                                # bitmap as a second parameter to OnSetBitmapEvent()
                                method (bitmap)
                    return
        event.Skip()

    def OnContextMenu(self, event):
        window = event.GetEventObject()
        if window is None:
            window = wx.Window_FindFocus()

        self._focusForContextMenu = window        
        try:
            while window is not None:
                blockItem = getattr (window, "blockItem", None)
                if blockItem is not None:
                    if hasattr(blockItem, "contextMenu"):
                        blockItem.widget.displayContextMenu(event)
                        return
                window = window.GetParent()
            event.Skip()
        finally:
            del self._focusForContextMenu

    def OnDestroyWindow(self, event):
        from osaf.framework.blocks.Block import Block
        Block.wxOnDestroyWidget (event.GetWindow())
        event.Skip()

    def OnShow(self, event):
        # Giant hack. Calling event.GetEventObject while the object is being created cause the
        # object to get the wrong type because of a "feature" of SWIG. So we need to avoid
        # OnShows in this case by using ignoreSynchronizeWidget as a flag.
        
        if not self.ignoreSynchronizeWidget:
            widget = event.GetEventObject()
            if hasattr(widget, 'blockItem') and \
               widget.IsShown() != event.GetShow():
                self.needsUpdateUI = True

        event.Skip()

    def propagateAsynchronousNotifications(self):
        view = self.UIRepositoryView
        view.dispatchQueuedNotifications()

        # synchronize dirtied blocks to reflect changes to the data
        from osaf.framework.blocks.Block import Block
        # make the list first in case it gets tweaked during synchronizeWidget
        dirtyBlocks = [view[theUUID] for theUUID in Block.dirtyBlocks]

        # synchronize affected widgets
        for block in dirtyBlocks:
            if block is not None:
                block.synchronizeWidget()

        Block.dirtyBlocks = set()

    def scheduleSave(self):
        # Schedule a call to save the focus block's value some number of seconds
        # in the future
        self.scheduledSaveTime = time.time() + 15

    def unscheduleSave(self):
        # Don't bother saving sometime in the future.
        self.scheduledSaveTime = None

    def commitSoon(self):
        # Set a flag to commit at the next idle
        self.doCommitSoon = True
        
    def OnIdle(self, event):
        if self.updateUIInOnIdle:
            count = 2
            while count:
                try:
                    self.UIRepositoryView.refresh()
                    self.propagateAsynchronousNotifications()
                    self.processSharingQueue(self.UIRepositoryView)
                except:
                    logger.exception("Error in OnIdle")
                    if Globals.options.catch != 'normal':
                        raise
                    elif count == 2:
                        wx.MessageBox(_(u'An application error occurred. Your unsaved changes will be lost while Chandler attempts to recover.'),
                                      _(u'Chandler Has Experienced An Error'))
                        self.UIRepositoryView.cancel()
                        count -= 1
                    elif count == 1:
                        wx.MessageBox(_(u'Chandler has experienced an error while recovering and needs to restart.'),
                                      _(u'Chandler Will Restart'))
                        self.restart()
                else:
                    break
        
        # Adding a handler for catching a set focus event doesn't catch
        # every change to the focus. It's difficult to preprocess every event
        # so we check for focus changes in OnIdle. Also call UpdateUI when
        # focus changes.

        focus = wxWindow_FindFocus()
        if self.focus != focus:
            self.focus = focus
            self.needsUpdateUI = True
        
        # is it time to auto-save changes to the focused block?
        scheduledSaveTime = getattr(self, 'scheduledSaveTime', None)
        if scheduledSaveTime is not None and \
           scheduledSaveTime <= time.time():
            from osaf.framework.blocks.Block import Block
            Block.finishEdits(commitToo=True, autoSaving=True)
            self.unscheduleSave()

        # Maybe it's time to commit (as triggered by proxies)
        # (This could coincidentally happen during the same idle as the
        # scheduled save above - this commit won't commit anything in that case,
        # but will be quick, so this comment is all I'm doing about it.)
        if getattr(self, 'doCommitSoon', False):
            self.UIRepositoryView.commit()
            del self.doCommitSoon

        if self.needsUpdateUI:
            try:
                for window in wx.GetTopLevelWindows():
                    if isinstance(window, wxBlockFrameWindow):
                        window.UpdateWindowUI(wx.UPDATE_UI_FROMIDLE |
                                              wx.UPDATE_UI_RECURSE)
            finally:
                self.needsUpdateUI = False

        # Give CPIA Script a chance to execute a script
        if not self.StartupScriptDone:
            self.StartupScriptDone = True
            import osaf.framework.scripting as Scripting
            wx.CallAfter(Scripting.run_startup_script, self.UIRepositoryView)

        event.Skip()

    StartupScriptDone = False

    def OnExit(self):
        """
        Main application termination. Called after the window is torn down.
        """
        # Close the repository
        self.UIRepositoryView.repository.close()

        from osaf.framework import MasterPassword
        from osaf.framework.twisted import waitForDeferred
        waitForDeferred(MasterPassword.clear())

        if self.CHANDLER_RESTART_ARGS is not None:
            # The spawn code must be executed after
            # the Repository.close() method
            # to prevent two instances of
            # Chandler from accessing the
            # same Repository and is
            # a fix for bug [Bug 11186] File-Reload
            # throws RepositoryOpenDeniedError and
            # crashes app
            self.spawnNewChandler(self.CHANDLER_RESTART_ARGS)

    def shutdown(self, repositoryCheck=True, repositoryCheckPoint=True,
                 restarting=False, forceBackup=False):
        """
        Shuts down Chandler Services and the Repository.

        Performs the following actions in order:
            1. Finishes any edits in progress
            2. Optionally export backup.chex
            3. Checks the Repository
            4. Shuts down the Mail Service
            5. Stops the Wake up Service
            6. Stops the Sharing layer
            7. Stops Twisted
            8. Commits the Repository
            9. Stops the M2Cypto layer
            10. Checkpoints the Repository
            11. Stops the Feedback Runtime log
        """
        
        # Finish any edits in progress.
        from osaf.framework.blocks.Block import Block
        Block.finishEdits()

        # Optionally save a backup.chex so that automatic migration will work
        from application.dialogs.Shutdown import ShutdownDialog
        # Optionally save a backup.chex so that automatic migration will work
        
        # Do not backup when running tests to save time; also prevents
        # the dialog from stopping tests.
        # There's also no reason to export if we are restarting.
        if (Globals.options.catch == 'tests') or restarting:
            backup = False
        else:
            prefs = schema.ns("osaf.app",
                              self.UIRepositoryView).prefs
            backup = getattr(prefs, 'backupOnQuit', True)

        dialog = ShutdownDialog(self.mainFrame, -1, rv=self.UIRepositoryView,
                                showCheckbox=not forceBackup)
        dialog.CenterOnParent()
        dialog.Show()
        
        
        # Do not backup when running tests to save time; also prevents
        # the dialog from stopping tests.
        # There's also no reason to export if we are restarting.
        if Globals.options.catch in ('tests') or restarting:
            backup = False
        elif forceBackup:
            backup = True
        else:
            prefs = schema.ns("osaf.app",
                              self.UIRepositoryView).prefs
            backup = getattr(prefs, 'backupOnQuit', True)

        if backup:
            path = os.path.join(Globals.options.profileDir, "backup.chex")
            dialog.RunBackup(path)

        # For some strange reason when there's an idle handler on the
        # application the mainFrame windows doesn't get destroyed, so
        # we'll remove the handler

        self.ignoreSynchronizeWidget = True

        if wx.Platform == '__WXMAC__':
            self.Bind(wx.EVT_ACTIVATE_APP, None)

        if __debug__ and repositoryCheck:
            dialog.Process(_(u"Verifying data..."), self.UIRepositoryView.check)

        if Globals.mailService is not None:
            # Ensure that the Globals.mailService has been initialized before
            # calling shutdown.
            dialog.Process(_(u"Shutting down mail..."),
                           Globals.mailService.shutdown)


        dialog.Process(_(u"Shutting down wakeup service..."),
                       Utility.stopWakeup)

        from osaf import sharing
        dialog.Process(_(u"Shutting down sharing..."),
                       sharing.interrupt, graceful=False)

        dialog.Process(_(u"Shutting down networking..."), Utility.stopTwisted)

        # Since Chandler doesn't have a save command and commits typically happen
        # only when the user completes a command that changes the user's data, we
        # need to add a final commit when the application quits to save data the
        # state of the user's world, e.g. window location and size.

        def commit(view):
            try:
                view.commit()
            except VersionConflictError, e:
                logger.exception(e)

        dialog.Process(_(u"Saving data..."), commit, self.UIRepositoryView)

        dialog.Process(_(u"Shutting down encryption..."),
                       Utility.stopCrypto, Globals.options.profileDir)

        if repositoryCheckPoint:
            dialog.Process(_(u"Checkpointing data..."),
                           self.UIRepositoryView.repository.checkpoint)

        feedback.stopRuntimeLog(Globals.options.profileDir)

        # Exit the main loop instead of deleting ourself so as to avoid events
        # firing when object are being deleted
        self.ExitMainLoop()

    def restart(self, *args, **kwds):
        """
        Restart the application.

        The application is restarted using the same command it was started
        with.

        Optional arguments passed in via C{args} are appended to the command 
        first.

        Optional named arguments passed in via C{kwds} are appended to the 
        command next - in no particular order - by pre-pending '--' to their
        name which must be a valid command line argument for the application. 

        Argument values may be of any type that can be represented as a
        string. Unicode values are encoded using the system's file system
        encoding. On Windows, values containing space characters are wrapped
        with C{\"} if there are not already. If a keyword argument's value is
        C{True}, only its name is appended to the command.

        For example: app.restart('--backup', restore=path, mvcc=True) would
                     produce a command line containing:
                     C{'--backup --restore=path --mvcc'}
        """
        windows = os.name == 'nt'

        encoding = sys.getfilesystemencoding()
        argv = []

        if not __debug__:
            argv.append('-O')

        skip = False
        for arg in sys.argv:
            if skip:
                skip = False
                continue
            if arg in ('-c', '--create', '--reset-index'):
                continue
            if arg in ('-r', '--restore', '--reload', '--undo'):
                skip = True
                continue
            if arg.startswith('--restore='):
                continue
            if arg.startswith('--reload='):
                continue
            if arg.startswith('--undo='):
                continue
            if windows and not arg.endswith('"') and ' ' in arg:
                arg = '"%s"' %(arg)
            argv.append(arg)

        for arg in args:
            if isinstance(arg, unicode):
                arg = arg.encode(encoding)
            elif not isinstance(arg, str):
                arg = str(arg)
            if windows and not arg.endswith('"') and ' ' in arg:
                arg = '"%s"' %(arg)
            argv.append(arg)

        for name, value in kwds.iteritems():
            if value is True:
                arg = '--%s' %(name)
            else:
                if isinstance(value, unicode):
                    value = value.encode(encoding)
                elif not isinstance(value, str):
                    value = str(value)
                if windows and not value.endswith('"') and ' ' in value:
                    value = '"%s"' %(value)
                arg = '--%s=%s' %(name, value)
            argv.append(arg)

        # Saving the restart argv values in
        # the CHANDLER_RESTART_ARGS class
        # instance signals to the OnExit
        # method to spawn a new Chandler process
        # after the Repository has been closed.
        #
        # The spawn code must be executed after
        # the Repository.close() method
        # to prevent two instances of
        # Chandler from accessing the
        # same Repository and is
        # a fix for bug [Bug 11186] File-Reload
        # throws RepositoryOpenDeniedError and
        # crashes app
        self.CHANDLER_RESTART_ARGS = argv

        # Shutdown the application service layers
        # and do not perform any repository
        # checking or checkpointing.
        self.shutdown(repositoryCheck=False, repositoryCheckPoint=False,
                      restarting=True)

    def spawnNewChandler(self, argv):
        windows = os.name == 'nt'
        mac = sys.platform == 'darwin'
        linux = sys.platform.startswith('linux')
        # [grant] Bug 12879:
        # On the Mac, we fork() to create a new process (it's not
        # 100% clear why), but in this case we should not execl() from
        # the parent process, or we could have a race condition with
        # two processes trying to open the repository exclusively.
        do_execl = True

        try:
            executable = sys.executable
            if windows and ' ' in executable:
                executable = '"%s"' %(executable)

            if mac:
                # 0 return from fork() <==> we're in the child process
                do_execl = (0 == os.fork())
            argv.append(self.startenv)
            if do_execl:
                os.execle(sys.executable, executable, *argv)
        except OSError, e:
            from errno import EOPNOTSUPP
            if not mac or e.args[0] != EOPNOTSUPP:
                logger.exception("while restarting")
        except:
            logger.exception("while restarting")


    def OnMainThreadCallbackEvent(self, event):
        """
        Fire off a custom event handler
        """
        event.lock.release()
        try:
            event.target(*event.args, **event.kwds)
        except TypeError:
            logger.error('OnMainThreadCallbackEvent event=%s <%s>' % \
                         (str(event), type(event)))
            raise
        event.Skip()

    def PostAsyncEvent(self, callback, *args, **kwds):
        """
        Post an asynchronous event that will call 'callback' with 'data'
        """
        evt = MainThreadCallbackEvent(callback, *args, **kwds)
        evt.lock.acquire()
        wx.PostEvent(self, evt)
        return evt.lock

    def _DispatchItemMethod (self, transportItem, methodName, transportArgs, keyArgs):
        """
        Private dispatcher for a method call on an item done between threads.
        
        See CallItemMethodAsync() below for calling details.
        
        Do a repository refresh to get the changes across from the other thread.
        """
        from osaf.framework.blocks.Block import Block

        self.UIRepositoryView.refresh() # bring changes across from the other thread/view

        # unwrap the target item and find the method to call

        if isinstance (transportItem, TransportWrapper):
            item = transportItem.unwrap ()
        else:
            item = Block.findBlockByName (transportItem)
            assert item is not None

        method = getattr (type(item), methodName, None)
        if method is None:
            logger.warning ("CallItemMethodAsync couldn't find method %s on item %s" % (methodName, str (item)))
        else:
            # unwrap the transportArgs
            args = []
            for wrapper in transportArgs:
                args.append (wrapper.unwrap())
    
            # unwrap the keyword args
            for key, wrapper in keyArgs.items():
                keyArgs[key] = wrapper.unwrap()
    
            # call the member with params
            method (item, *args, **keyArgs)

    def CallItemMethodAsync (self, item, methodName, *args, **keyArgs):
        """
        Post an asynchronous event that will call a method by name in an item.
        If item is a string then the block of that name will be used as the
        item.
        
        Communication between threads is tricky.  This method will convert
        all parameters into UUIDs for transport during the event posting,
        and they will be converted back to items when the event is received.
        However you will have to do a commits in the non-UI thread for the data
        to pass across smoothly.  The UI thread will do a commit to get
        the changes on its side.  
        
        Also, items that are not simple arguments or keyword arguments will 
        not be converted to/from UUID.

        All other args are passed across to the other thread.
        
        @param item: an C{Item} whose method we wish to call
        @type item: C{Item} or C{String}
        @param methodName: the name of the method to call
        @type methodName: C{String}
        """
        # convert the item whose method we're calling
        if isinstance (item, schema.Item):
            item = TransportWrapper (item)
        # convert all the arg items
        transportArgs = []
        for anItem in args:
            transportArgs.append (TransportWrapper (anItem))
        # convert all dictionary items
        for key,value in keyArgs.items():
            keyArgs[key] = TransportWrapper (value)
        self.PostAsyncEvent (self._DispatchItemMethod, item, 
                                    methodName, transportArgs, keyArgs)


    def ShowPlatformMismatchWindow(self, origName, currentName):
        logger.info("Repository platform mismatch: (orig %s vs now %s)",
                    origName, currentName)

        osNames = { 'darwin-i386': 'Intel Mac OS X',
                    'darwin-ppc': 'Power PC Mac OS X',
                    'linux-i386': 'Linux',
                    'win32-i386': 'Windows XP' }
        origName = osNames.get(origName, origName)
        currentName = osNames.get(currentName, currentName)

        message = _(u"""Your data was created on %(origOperatingSystem)s and is incompatible with Chandler on %(currentOperatingSystem)s. To transfer your data over to %(currentOperatingSystem)s:

1. On your %(origOperatingSystem)s computer, start up Chandler and go to the File>>Export Collections and Settings... menu to export your data.

2. Move the .chex export file to your %(currentOperatingSystem)s computer.

3. On your %(currentOperatingSystem)s computer, start up Chandler and click 'Yes' when you encounter this dialog again.

4. Go to the File>>Reload Collections and Settings... menu to reload your data by pointing Chandler to the .chex export file from your %(origOperatingSystem)s computer.

Do you want to start Chandler with a fresh data repository?""") %{'origOperatingSystem': origName,
                                                                  'currentOperatingSystem': currentName}

        dialog = wx.MessageDialog(None, message,
                                  _(u"Cannot open repository."),
                                  wx.YES_NO | wx.ICON_INFORMATION)
        response = dialog.ShowModal()
        dialog.Destroy()
        return response == wx.ID_YES

    def RunRecordedScript (self, events):
        from osaf.framework.script_recording.script_lib import InitializeScript
        self.events = events
        self.eventsIndex = 0
        InitializeScript()
        if len (events) > 0:
            self.SetPlaybackEventPending (True)
            while self.PlaybackEventPending():
                self.ProcessPlaybackEvent()

            
    def ProcessPlaybackEvent (self):
        from osaf.framework.script_recording.script_lib import ProcessEvent
        eventsIndex = self.eventsIndex
        self.eventsIndex = eventsIndex + 1
        ProcessEvent (*self.events [eventsIndex])
        if self.eventsIndex >= len (self.events):
            self.SetPlaybackEventPending (False)
            self.events = [] # Release storage of events


class TransportWrapper (object):
    """
    Wrapper class for items sent between threads by
    CallItemMethodAsync() in wxApplication.
    
    Simply wraps any object with this class.  If the 
    object was an Item, we remember its UUID and
    use that to get back the right item on in the
    other thread/view.
    """
    def __init__ (self, possibleItem):
        """
        Construct a TransportWrapper from an object.
        """
        if isinstance(possibleItem, schema.Annotation):
            self.annotationClass = type(possibleItem)
            possibleItem = possibleItem.itsItem

        try:
            self.itemUUID = possibleItem.itsUUID
        except AttributeError:
            self.nonItem = possibleItem

    def unwrap (self):
        """
        Unwrap the original object, using the UUID
        if the original was an Item.
        """
        try:
            theUUID = self.itemUUID
        except AttributeError:
            return self.nonItem

        item = wx.GetApp().UIRepositoryView.findUUID(theUUID)
        try:
            return self.annotationClass(item)
        except (TypeError, AttributeError):
            return item

class StartupSplash(wx.Frame):
    DEFAULT_STYLE = wx.DOUBLE_BORDER if wx.Platform == '__WXGTK__' else wx.SIMPLE_BORDER
    def __init__(self, parent, bmp):
        padding = 7     # padding under and right of the progress percent text (in pixels)
        fontsize = 10   # font size of the progress text (in pixels)
        self.progressWrap = 210 # If progress message is longer than this, it gets wrapped
        
        super(StartupSplash, self).__init__(parent=parent,
                                            title=_(u'Starting Chandler...'),
                                            style=self.DEFAULT_STYLE)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)
        self.CenterOnScreen()
        self.SetBackgroundColour(wx.WHITE)

        icon = wx.Icon("Chandler.egg-info/resources/icons/Chandler_32.ico", wx.BITMAP_TYPE_ICO)
        self.SetIcon(icon)
        
        # Progress Text dictionary
        #                    name            weight      text
        
        self.statusTable = { #L10N: Starting the SSL and password encryption services
                            'crypto'      : ( 10, _(u"Starting encryption...")),
                            # L10N: Opening the Chandler Repository
                            'repository'  : ( 10, _(u"Opening data...")),
                            # L10N: Loading the Chandler code modules (parcels)
                            'parcels'     : ( 15, _(u"Loading plugins...")),
                            'twisted'     : ( 10, _(u"Starting networking...")),
                            # L10N: The main view is the core piece of UI that represents
                            #       the majority of the widgets displayed on the screen.
                            'mainview'    : ( 10, _(u"Building application view...")),
                            # L10N: The main view is the core piece of UI that represents
                            #       the majority of the widgets displayed on the screen.
                            'layout'      : ( 15, _(u"Building application view...")),
                            'commit'      : ( 10, _(u"Saving changes...")),
                            # L10N: There are a number of background services that Chandler
                            #       runs for Sharing, Mail, etc
                            'services'    : ( 10, _(u"Starting mail and sharing...")),
                            }

        # Font to be used for the progress text
        font = wx.Font(fontsize, wx.SWISS, wx.NORMAL, wx.NORMAL)
        
        # Load the splash screen picture.
        # The picture will set the width of the splash screen, 
        # all other elements are horizontally centered on it (except for the progress "%" display)
        bitmap = wx.StaticBitmap(self, -1, bmp)
        sizer.Add(bitmap, 0, wx.ALIGN_CENTER, 0)

        # Add Chandler text
        text1 = wx.StaticText(self, -1, (u"Chandler\u2122")) # Chandler TM
        text1.SetBackgroundColour(wx.WHITE)
        sizer.Add(text1, 1,  wx.ALIGN_CENTER)
        text1.SetFont(wx.Font(16, wx.SWISS, wx.NORMAL, wx.BOLD))

        # Add Version text
        text2 = wx.StaticText(self, -1,
                              _(u"Version %(version)s") % { 'version': version })
        text2.SetBackgroundColour(wx.WHITE)
        sizer.Add(text2, 1,  wx.ALIGN_CENTER)
        text2.SetFont(font)

        # Add OSAF text, this also sets window width, being the longest string
        text3 = wx.StaticText(self, -1, (u"Open Source Applications Foundation"))
        text3.SetBackgroundColour(wx.WHITE)
        sizer.Add(text3, 1,  wx.ALIGN_CENTER)
        text3.SetFont(wx.Font(12, wx.SWISS, wx.NORMAL, wx.NORMAL))

        # The progress text is in 2 parts: a text indicating the section being initialized
        # and a percent number indicating an approximate value of the total being done
        # Create the text box for the section initialized text
        self.progressText = wx.StaticText(self, -1, style=wx.TE_CENTER)
        self.progressText.SetBackgroundColour(wx.WHITE)

        progressSizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(progressSizer, 1, wx.EXPAND)
        # In order to center the progress text, we need to add a dummy item on the left
        # that has the same weight as the progress percent on the right
        progressSizer.Add((padding, padding), 1)
        progressSizer.Add(self.progressText, 0, wx.ALIGN_CENTER_HORIZONTAL)
        self.progressText.SetFont(font)
        self.progressText.MinSize = (self.progressWrap,
                                     self.progressText.MinSize.height)
        self.progressText.Wrap(self.progressWrap)

        # Create the text box for the "%" display
        self.progressPercent = wx.StaticText(self, -1, style=wx.ALIGN_RIGHT)
        self.progressPercent.SetBackgroundColour(wx.WHITE)
        progressSizer.Add(self.progressPercent, 1, wx.ALIGN_RIGHT | wx.RIGHT, padding)
        self.progressPercent.SetFont(font)
        
        # Add extra whitespace below for wrapping progress text
        text4 = wx.StaticText(self, -1, "")
        text4.SetBackgroundColour(wx.WHITE)
        sizer.Add(text4, 1,  wx.ALIGN_CENTER)
        text4.SetFont(font)

        self.workingTicks = 0
        self.completedTicks = 0
        
        sizer.SetSizeHints(self)
        self.Layout()
        
    def fixedMessage(self, message):
        self.progressText.SetLabel(message)
        self.Update()
        wx.GetApp().Yield(True)

    def updateGauge(self, type):
        self.completedTicks += self.workingTicks
        self.workingTicks = self.statusTable[type][0]
        self.progressText.SetLabel(self.statusTable[type][1])
        percentString = u"%d%%" % self.completedTicks
        self.progressPercent.SetLabel(percentString)
        self.progressText.Wrap(self.progressWrap)

        self.Layout()
        self.Update()
        wx.GetApp().Yield(True)


def checkMacPlatform():
    """
    Check that we're not running the wrong Mac binaries for the Mac hardware
    """

    if sys.platform == 'darwin':
        from platform import processor, machine
        if processor() == 'i386' and machine() == 'Power Macintosh':
            # running under Rosetta, not supported
            return False

    return True
