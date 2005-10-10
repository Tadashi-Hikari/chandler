import os, sys
import traceback
import logging
import wx
import wx.xrc
from osaf import sharing
import application.Globals as Globals
import application.dialogs.Util
import application.Parcel
from i18n import OSAFMessageFactory as _
from application import schema
from AccountInfoPrompt import PromptForNewAccountInfo

logger = logging.getLogger(__name__)

SHARING = "osaf.sharing"
CONTENTMODEL = "osaf.pim"

class SubscribeDialog(wx.Dialog):

    def __init__(self, parent, title, size=wx.DefaultSize,
         pos=wx.DefaultPosition, style=wx.DEFAULT_DIALOG_STYLE,
         resources=None, view=None, url=None):

        wx.Dialog.__init__(self, parent, -1, title, pos, size, style)

        self.view = view
        self.resources = resources
        self.parent = parent

        self.mySizer = wx.BoxSizer(wx.VERTICAL)
        self.toolPanel = self.resources.LoadPanel(self, "Subscribe")
        self.mySizer.Add(self.toolPanel, 0, wx.GROW|wx.ALL, 5)

        self.statusPanel = self.resources.LoadPanel(self, "StatusPanel")
        self.statusPanel.Hide()
        self.accountPanel = self.resources.LoadPanel(self, "UsernamePasswordPanel")
        self.accountPanel.Hide()

        self.SetSizer(self.mySizer)
        self.mySizer.SetSizeHints(self)
        self.mySizer.Fit(self)

        self.textUrl = wx.xrc.XRCCTRL(self, "TEXT_URL")
        if url is not None:
            self.textUrl.SetValue(url)
        else:
            account = sharing.schema.ns('osaf.app', self.view).currentWebDAVAccount.item
            if account:
                url = account.getLocation()
                self.textUrl.SetValue(url)

        self.Bind(wx.EVT_TEXT, self.OnTyping, self.textUrl)

        self.textStatus = wx.xrc.XRCCTRL(self, "TEXT_STATUS")
        self.textUsername = wx.xrc.XRCCTRL(self, "TEXT_USERNAME")
        self.textPassword = wx.xrc.XRCCTRL(self, "TEXT_PASSWORD")
        self.checkboxKeepOut = wx.xrc.XRCCTRL(self, "CHECKBOX_KEEPOUT")

        self.Bind(wx.EVT_BUTTON, self.OnSubscribe, id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self.OnCancel, id=wx.ID_CANCEL)

        self.SetDefaultItem(wx.xrc.XRCCTRL(self, "wxID_OK"))


        self.textUrl.SetFocus()
        self.textUrl.SetInsertionPointEnd()


    def accountInfoCallback(self, host, path):
        return PromptForNewAccountInfo(self, host=host, path=path)

    def OnSubscribe(self, evt):
        view = self.view
        url = self.textUrl.GetValue()
        if url.startswith('webcal:'):
            url = 'http:' + url[7:]

            self.__showStatus(_(u"You are already subscribed"))
            return

        try:

            self.__showStatus(_(u"In progress..."))
            wx.Yield()

            if self.accountPanel.IsShown():
                username = self.textUsername.GetValue()
                password = self.textPassword.GetValue()
                collection = sharing.subscribe(view, url,
                    accountInfoCallback=self.accountInfoCallback,
                    username=username, password=password)
            else:
                collection = sharing.subscribe(view, url,
                    accountInfoCallback=self.accountInfoCallback)

            if collection is None:
                # user cancelled out of account dialog
                return

            # Keep this collection out of "My items" if checked:
            if self.checkboxKeepOut.GetValue():
                logger.info(_(u'Moving collection out of My Items'))
                schema.ns('osaf.app', view).notMine.addSource(collection)

            assert (hasattr (collection, 'color'))
            schema.ns("osaf.app", view).sidebarCollection.add (collection)
            # Need to SelectFirstItem -- DJA
            share = sharing.getShare(collection)

            event = 'ApplicationBarAll'
            if share.filterClasses and len(share.filterClasses) == 1:
                filterClass = share.filterClasses[0]
                if filterClass == 'osaf.pim.calendar.Calendar.CalendarEventMixin':
                    event = 'ApplicationBarEvent'
                elif filterClass == 'osaf.pim.tasks.TaskMixin':
                    event = 'ApplicationBarTask'
                elif filterClass == 'osaf.pim.mail.MailMessageMixin':
                    event = 'ApplicationBarMail'

            Globals.views[0].postEventByName(event, {})

            self.EndModal(True)

        except sharing.NotAllowed, err:
            self.__showAccountInfo()
        except sharing.NotFound, err:
            self.__showStatus(_(u"That collection was not found"))
        except sharing.AlreadySubscribed, err:
            self.__showStatus(_(u"You are already subscribed"))
        except sharing.SharingError, err:
            logger.exception("Error during subscribe for %s" % url)
            self.__showStatus(_(u"Sharing Error:\n%(error)s") % {'error': err})
        except Exception, e:
            logger.exception("Error during subscribe for %s" % url)
            self.__showStatus(_(u"Sharing Error:\n%(error)s") % {'error': e})

    def OnTyping(self, evt):
        self.__hideStatus()
        self.__hideAccountInfo()


    def __showAccountInfo(self):
        self.__hideStatus()

        if not self.accountPanel.IsShown():
            self.mySizer.Add(self.accountPanel, 0, wx.GROW, 5)
            self.accountPanel.Show()
            self.textUsername.SetFocus()

        self.__resize()

    def __hideAccountInfo(self):

        if self.accountPanel.IsShown():
            self.accountPanel.Hide()
            self.mySizer.Detach(self.accountPanel)
            self.__resize()

    def __showStatus(self, text):
        self.__hideAccountInfo()

        if not self.statusPanel.IsShown():
            self.mySizer.Add(self.statusPanel, 0, wx.GROW, 5)
            self.statusPanel.Show()

        self.textStatus.SetLabel(text)
        self.__resize()

    def __hideStatus(self):
        if self.statusPanel.IsShown():
            self.statusPanel.Hide()
            self.mySizer.Detach(self.statusPanel)
            self.__resize()

    def __resize(self):
        self.mySizer.Layout()
        self.mySizer.SetSizeHints(self)
        self.mySizer.Fit(self)


    def OnCancel(self, evt):
        self.EndModal(False)

def Show(parent, view=None, url=None):
    xrcFile = os.path.join(Globals.chandlerDirectory,
     'application', 'dialogs', 'SubscribeCollection_wdr.xrc')
    #[i18n] The wx XRC loading method is not able to handle raw 8bit paths
    #but can handle unicode
    xrcFile = unicode(xrcFile, sys.getfilesystemencoding())
    resources = wx.xrc.XmlResource(xrcFile)
    win = SubscribeDialog(parent, _(u"Subscribe to Shared Collection"),
     resources=resources, view=view, url=url)
    win.CenterOnScreen()
    win.ShowModal()
    win.Destroy()
