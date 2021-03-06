#   Copyright (c) 2006-2008 Open Source Applications Foundation
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

import os, sys, time, codecs, platform
from cgi import escape
import wx
from i18n import ChandlerSafeTranslationMessageFactory as _
import Globals
import version
from feedback_xrc import *

LOGLINES = 500

destroyAppOnClose = False

def initRuntimeLog(profileDir):
    """
    Append the current time as application start time to run time log,
    creating the log file if necessary.
    """
    try:
        f = open(os.path.join(profileDir, 'start.log'), 'a+')
        f.write('start:%s\n' % long(time.time()))
        f.close()
    except:
        pass


def stopRuntimeLog(profileDir):
    """
    Append the current time as application stop time.
    """
    try:
        logfile = os.path.join(profileDir, 'start.log') 
        f = open(logfile, 'a+')
        f.write('stop:%s\n' % long(time.time()))
        f.close()
        return logfile
    except:
        pass


class FeedbackWindow(wx.PyOnDemandOutputWindow):
    """
    An error dialog that would be shown in case there is an uncaught
    exception. The user can send the error report back to us as well.
    """
    def __call__(self, *args, **kw):
        # Make this a Singleton to avoid the problem of multiple feedback
        # windows popping up at the same time
        return self

    def _do_write(self, text):
        app = wx.GetApp()
        view = getattr(app, 'UIRepositoryView', None)
        refreshErrors = getattr(view, 'refreshErrors', 0)

        # if more than 3 refreshErrors on view, make frame modal and
        # change the "Close" button to "Quit"
        self.noContinue(refreshErrors > 3)

        wx.PyOnDemandOutputWindow.write(self, text)

    def write(self, text):
        if not wx.Thread_IsMain():
            wx.CallAfter(self._do_write, text)
        else:
            self._do_write(text)

    def noContinue(self, noContinue):
        if self.frame is None:
            self.CreateOutputWindow('')

        self.frame.MakeModal(noContinue)
        if noContinue:
            global destroyAppOnClose
            destroyAppOnClose = True
            self.frame.closeButton.SetLabel(_(u'&Quit'))
        self.frame.disableFeedback.Enable(not noContinue)

    def _fillOptionalSection(self):
        try:    
            # columns
            self.frame.sysInfo.InsertColumn(0, 'key')
            self.frame.sysInfo.InsertColumn(1, 'value')

            # data
            self.frame.sysInfo.InsertStringItem(0, 'os.getcwd')
            self.frame.sysInfo.SetStringItem(0, 1, '%s' % os.getcwd())
            index = 1
            self.frame.sysInfo.InsertStringItem(index, 'sys.executable')
            self.frame.sysInfo.SetStringItem(index, 1, '%s' % sys.executable)
            index += 1
            for argv in sys.argv:
                self.frame.sysInfo.InsertStringItem(index, 'sys.argv')
                self.frame.sysInfo.SetStringItem(index, 1, '%s' % argv)
                index += 1
            for path in sys.path:
                self.frame.sysInfo.InsertStringItem(index, 'sys.path')
                self.frame.sysInfo.SetStringItem(index, 1, '%s' % path)
                index += 1
            for key in os.environ.keys():
                self.frame.sysInfo.InsertStringItem(index, 'os.environ')
                self.frame.sysInfo.SetStringItem(index, 1, '%s: %s' % (key, os.environ[key]))
                index += 1
            try:
                f = codecs.open(os.path.join(Globals.options.profileDir,
                                             'chandler.log'),
                                encoding='utf-8', mode='r', errors='ignore')
                for line in f.readlines()[-LOGLINES:]:
                    self.frame.sysInfo.InsertStringItem(index, 'chandler.log')
                    self.frame.sysInfo.SetStringItem(index, 1, '%s' % line.strip())
                    index += 1
            except:
                pass

            self.frame.sysInfo.SetColumnWidth(0, wx.LIST_AUTOSIZE)
            self.frame.sysInfo.SetColumnWidth(1, wx.LIST_AUTOSIZE)
        except:
            pass

        self.frame.delButton.Bind(wx.EVT_BUTTON, self.OnDelItem, self.frame.delButton)
        self.frame.sysInfo.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown)

        self.frame.sysInfo.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnItemSelected)
        self.frame.sysInfo.Bind(wx.EVT_LIST_ITEM_DESELECTED, self.OnItemDeselected)

    def OnItemSelected(self, event):
        self.frame.delButton.Enable()

    def OnItemDeselected(self, event):
        if self.frame.sysInfo.GetSelectedItemCount() < 1:
            self.frame.delButton.Disable()
            # Disabling the focused button disables keyboard navigation
            # unless we set the focus to something else - let's put it
            # on the list control.
            self.frame.sysInfo.SetFocus()

    def OnKeyDown(self, event):
        if event.GetKeyCode() == wx.WXK_DELETE:
            return self.OnDelItem(event)
        event.Skip()

    def OnDelItem(self, event):
        while True:
            index = self.frame.sysInfo.GetNextItem(-1, state=wx.LIST_STATE_SELECTED)
            if index < 0:
                break
            self.frame.sysInfo.DeleteItem(index)

    def _fillRequiredSection(self, st):
        # Time since last failure
        try:
            logfile = stopRuntimeLog(Globals.options.profileDir)
            try:
                timeSinceLastError = 0
                start = 0
                for line in open(logfile):
                    verb, value = line.split(':')
                    # We may have corrupted start, start; stop, stop entries but that is ok,
                    # we only count the time between start, stop pairs.
                    if verb == 'start':
                        start = long(value)
                    elif start != 0:
                        stop = long(value)
                        if stop > start: # Skip over cases where we know system clock has changed
                            timeSinceLastError += stop - start
                        start = 0
            except:
                timeSinceLastError = 0
            
            self.frame.text.AppendText('Seconds since last error: %d\n' % timeSinceLastError)
            
            # Clear out the logfile
            f = open(logfile, 'w')
            f.close()
        except:
            pass
        
        # Version and other miscellaneous information
        try:
            self.frame.text.AppendText('Chandler Version: %s\n' % version.version)
            
            self.frame.text.AppendText('OS: %s\n' % os.name)
            self.frame.text.AppendText('Platform Type: %s\n' % sys.platform)
            self.frame.text.AppendText('Platform Details: %s\n' % platform.platform())
            self.frame.text.AppendText('Architecture: %s\n' % platform.machine())
            self.frame.text.AppendText('Python Version: %s\n' % sys.version)
        except:
            pass
        
        # Traceback (actually just the first line of it)
        self.frame.text.AppendText(st)

    def CreateOutputWindow(self, st):
        self.frame = xrcFRAME(None)
        self.text = self.frame.text # superclass expects self.text
        try:
            icon = wx.Icon("Chandler.egg-info/resources/icons/Chandler_32.ico", wx.BITMAP_TYPE_ICO)
            self.frame.SetIcon(icon)
        except:
            pass
        
        self._fillRequiredSection(st)
        self._fillOptionalSection()
        self.frame.delButton.Disable()
        
        size = wx.Size(450, 400)
        self.frame.SetMinSize(size)
        self.frame.Fit()
        self.frame.Show(True)
        
        self.frame.Bind(wx.EVT_CHAR, self.OnChar)
        self.frame.Bind(wx.EVT_CLOSE, self.OnCloseWindow)
        self.frame.Bind(wx.EVT_BUTTON, self.OnCloseWindow, self.frame.closeButton)
        self.frame.Bind(wx.EVT_BUTTON, self.OnSend, self.frame.sendButton)
        self.frame.Bind(wx.EVT_BUTTON, self.OnRestart, self.frame.restartButton)

    def forceQuit(self):
        try:
            # This part is needed to quit on OS X
            from osaf.framework.blocks.Block import Block
            Block.postEventByNameWithSender ("Quit", {})
        finally:
            sys.exit()

    def OnCloseWindow(self, event):
        if self.frame.disableFeedback.IsChecked():
            wx.GetApp().RestoreStdio()
        global activeWindow
        wx.PyOnDemandOutputWindow.OnCloseWindow(self, event)
        activeWindow = None
        if destroyAppOnClose:
            self.forceQuit()
        initRuntimeLog(Globals.options.profileDir)

    def OnChar(self, event):
        # Close the window if an escape is typed
        keycode = event.GetKeyCode()
        if keycode == wx.WXK_ESCAPE:
            self.OnCloseWindow(event)
        else:
            event.Skip()

    def OnRestart(self, event):
        try:
            self.frame.sendButton.Disable()
            self.frame.restartButton.Disable()
            self.frame.closeButton.Disable() 
            self.frame.restartButton.SetLabel(_(u'Restarting...'))
    
            import atexit
            atexit.register(restart)
        finally:
            self.forceQuit()

    def logReport(self, feedbackXML, serverResponse):
        try:
            # chandler.log
            import logging
            logger = logging.getLogger(__name__)
            logger.info(serverResponse)
            
            # Extract the actual report ID. Response looks like this:
            # desktop feedback submission #2006-09-07T13-25-10.279322 successful.
            import re
            feedbackId = re.compile('^.*(\d{4}\-\d{2}\-\d{2}T\d{2}\-\d{2}\-\d{2}\.\d{6}).*$').match(serverResponse).group(1)
            
            # Show the ID so that users can report it in bugs etc.
            # L10N: The numerical ID of a feedback report generated
            #       by Chandler when an error occurs. The ID is
            #       used to report and track the bug.
            self.frame.text.AppendText(_(u'\nFeedback report ID: %(feedbackId)s') % {'feedbackId': feedbackId})
                        
            # Log each report to a new file
            feedbackFile = os.path.join(Globals.options.profileDir, 'feedback-%s.xml' % feedbackId)
            f = open(feedbackFile, 'w')
            f.write(feedbackXML)
            f.close()

            # Show the path to the saved file
            # L10N: The feedback report contains debugging information
            #       used by the Chandler team to resolve a bug or issue
            #       discovered by the user.
            self.frame.text.AppendText(_(u"\nYour feedback report has been saved locally at: %(feedbackFile)s") \
                                       % {'feedbackFile': feedbackFile})

        except:
            pass

    def OnSend(self, event):
        self.frame.sendButton.Disable()
        # Disabling the focused button disables keyboard navigation
        # unless we set the focus to something else - let's put it
        # on close button
        self.frame.closeButton.SetFocus() 
        self.frame.sendButton.SetLabel(_(u'Sending...'))
        
        try:
            from M2Crypto import httpslib, SSL
            # Try to load the CA certificates for secure SSL.
            # If we can't load them, the data is hidden from casual observation,
            # but a man-in-the-middle attack is possible.
            ctx = SSL.Context()
            opts = {}
            if ctx.load_verify_locations('parcels/osaf/framework/certstore/cacert.pem') == 1:
                ctx.set_verify(SSL.verify_peer | SSL.verify_fail_if_no_peer_cert, 9)
                opts['ssl_context'] = ctx
            c = httpslib.HTTPSConnection('feedback.osafoundation.org', 443, opts)
            body = buildXML(self.frame.comments, self.frame.email,
                            self.frame.sysInfo, self.frame.text)
            c.request('POST', '/desktop/post/submit', body)
            response = c.getresponse()
            
            if response.status != 200:
                raise Exception('response.status=' + response.status)
            c.close()
        except:
            self.frame.sendButton.SetLabel(_(u'Failed to send'))
        else:
            self.frame.sendButton.SetLabel(_(u'Sent'))
            self.logReport(body, response.read())
                
FeedbackWindow = FeedbackWindow()

def buildXML(comments, email, optional, required):
    """
    Given the possible fields in the error dialog, build an XML file
    of the data.
    """
    ret = ['<feedback xmlns="http://osafoundation.org/xmlns/feedback" version="0.4">']
    
    # The required field consists of field: value lines, followed by either
    # traceback or arbitrary output that was printed to stdout or stderr.
    lastElem = ''
    for line in required.GetValue().split('\n'):
        if lastElem == '':
            sep = line.find(':')
            if line.startswith('Traceback'):
                lastElem = 'traceback'
                ret.append('<%s>' % lastElem)
                ret.append(escape(line))
            elif sep < 0:
                lastElem = 'output'
                ret.append('<%s>' % lastElem)
                ret.append(escape(line))
            else:
                field = line[:sep].replace(' ', '-')
                value = line[sep + 1:].strip()
                ret.append('<%s>%s</%s>' % (field, escape(value), field))
        else:
            ret.append(escape(line))
    if lastElem != '':
        ret.append('</%s>' % lastElem)
    
    # Optional email
    ret.append('<email>%s</email>' % escape(email.GetValue()))
    
    # Optional comments
    ret.append('<comments>')
    ret.append(escape(comments.GetValue()))
    ret.append('</comments>')
    
    # Optional system information and logs
    for i in range(optional.GetItemCount()):
        field = optional.GetItem(i, 0).GetText()
        value = optional.GetItem(i, 1).GetText()
        ret.append('<%s>%s</%s>' % (field, escape(value), field))

    ret.append('</feedback>')
    
    s = '\n'.join(ret)
    
    if isinstance(s, unicode):
        s = s.encode('utf8')
    
    return s

def restart():
    try:
        import subprocess
        
        # argv[0] == Chandler.py
        args = sys.argv[1:]
        
        # We obviously want to avoid silently blowing the repository
        while '--create' in args:
            args.remove('--create')
        while '-c' in args:
            args.remove('-c')
        while '--reload' in args:
            args.remove('--reload')
        
        if wx.Platform == '__WXGTK__' and \
            Globals.options.locale is None:
            # Restarted Chandler fails to find locale, so
            # work around that issue by explicitly adding
            # locale option. See bug 6668 for more information.
            import i18n
            args.append('--locale=%s' % i18n.getLocale())
        elif sys.platform == 'darwin':
            # If you start Chandler using the .app bundle, the restarted
            # application fails to find display. Work around this by
            # switching to the way Chandler is started from the command
            # line. See bug 6681 for more information.
            cmdLineStart = sys.executable.rfind('/Python.app/Contents/MacOS/python') > 0
            if not cmdLineStart:
                cwd = os.getcwd() # .. Chandler.app/Contents/Resources
                p = '/Library/Frameworks/Python.framework/Versions/' + sys.version[:3] + '/Resources/Python.app/Contents/MacOS/Python'
                # XXX There is no way to detect if the running python
                # XXX interpreter was compiled optimized or not.
                # XXX So we fudge. The assumption is that we would never
                # XXX have both debug and release bits installed in the
                # XXX exact same location.
                if os.path.isdir(os.path.join(cwd, 'release')):
                    sys.executable = cwd + '/release' + p
                else:
                    sys.executable = cwd + '/debug' + p

        # Ask the user for the (recovery) options
        if '--ask' not in args:
            args.append('--ask')
            
        if not os.path.basename(sys.executable).startswith('chandler'):
            args.insert(0, sys.argv[0]) # Python needs Chandler.py
            
        subprocess.Popen([sys.executable] + args)
    except:
        pass
    
