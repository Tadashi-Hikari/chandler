
#   Copyright (c) 2005-2007 Open Source Applications Foundation
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


"""Contains base classes utilized by the Mail Service concrete classes"""

#twisted imports
import twisted.internet.reactor as reactor
import twisted.internet.defer as defer
import twisted.internet.error as error
import twisted.internet.protocol as protocol
import twisted.python.failure as failure
from M2Crypto.SSL.Checker import WrongHost

#python imports
import logging
import email
import email.Utils as emailUtils

#Chandler imports
from application import Globals
from chandlerdb.persistence.RepositoryView import RepositoryView
from osaf.pim.mail import AccountBase
from osaf.framework.certstore import ssl
import application.Utility as Utility
from osaf import messages

#Chandler Mail Service imports
import errors
import constants
from utils import *
import mailworker
import message


class DownloadVars(object):
    """
       This class contains the non-persisted
       DownloadAccount variables that are used
       during the downloading of mail.
    """

    def __init__(self):
        self.numDownloaded   = 0
        self.numToDownload   = 0

        # the total number of messages downloaded
        self.totalDownloaded = 0

        # the total number of messages to downloaded
        self.totalToDownload = 0

        # The list of pending messages to download
        self.pending = []

        # List of protocol UID's to delete from the
        # mail server. This is used for the case
        # where the user wants to delete the
        # messages on the server once they have
        # been downloaded to Chandler.
        self.delList = []

        # The messages list contains a tuples:
        # 0: Mail Request Tuple containing
        #    0: headers dict decoded and converted to unicode
        #    1: body of the message ready for assigning to the
        #       ContentItem.body attribute or None
        #    2: eim attachment decode and strip of carriage returns
        #       or None
        #    3: ics attachment decode and strip of carriage returns
        #       or None
        #
        # 1: Protocol specific server UID
        self.messages = []


class AbstractDownloadClientFactory(protocol.ClientFactory):
    """ Base class for Chandler download transport factories(IMAP, POP, etc.).
        Encapsulates boiler plate logic for working with Twisted Client Factory
        disconnects and Twisted protocol creation"""

    # Base exception that will be raised on error.
    # can be overidden for use by subclasses.
    exception = errors.MailException

    def __init__(self, delegate):
        """
        @param delegate: A Chandler protocol class containing:
          1. An account object inherited from c{AccountBase}
          2. A loginClient method implementation callback
          3. A catchErrors method implementation errback
        @type delegate: c{object}

        @return: C{None}
        """

        self.delegate = delegate
        self.connectionLost = False
        self.sendFinished = 0
        self.useTLS = (delegate.account.connectionSecurity == 'TLS')
        self.timeout = constants.TIMEOUT
        self.timedOut = False

        retries = delegate.account.numRetries

        assert isinstance(retries, (int, long))
        self.retries = -retries

    def buildProtocol(self, addr):
        """
        Builds a Twisted Protocol instance assigning factory
        and delegate as variables on the protocol instance

        @param addr: an object implementing L{twisted.internet.interfaces.IAddress}

        @return: an object extending  L{twisted.internet.protocol.Protocol}
        """
        p = protocol.ClientFactory.buildProtocol(self, addr)

        #Set up a reference so delegate can call the proto and proto
        #can call the delegate.

        p.delegate = self.delegate
        self.delegate.proto = p

        #Set the protocol timeout value to that specified in the account
        p.timeout = self.timeout
        p.factory  = self

        return p

    def clientConnectionFailed(self, connector, err):
        """
          Called when a connection has failed to connect.

          @type err: L{twisted.python.failure.Failure}
        """
        if __debug__:
            trace("ClientConnectionFailed")

        self._processConnectionError(connector, err)

    def clientConnectionLost(self, connector, err):
        """
          Called when an established connection is lost.

          @type err: L{twisted.python.failure.Failure}
        """
        if __debug__:
            trace("ClientConnectionLost")

        self._processConnectionError(connector, err)


    def _processConnectionError(self, connector, err):
        self.connectionLost = True

        if self.delegate.errorHandled:
            self.delegate._resetClient()

        elif self.retries < self.sendFinished <= 0:
            if __debug__:
                trace("**Connection Lost** Retrying server. Retry: %s" % -self.retries)

            connector.connect()
            self.retries += 1

        elif self.sendFinished <= 0:
            if err.check(error.ConnectionDone):
                err.value = self.exception(constants.MAIL_PROTOCOL_CONNECTION_ERROR)

            self.delegate.catchErrors(err)

class AbstractDownloadClient(object):
    """ Base class for Chandler download transports (IMAP, POP, etc.)
        Encapsulates logic for interactions between Twisted protocols (POP, IMAP)
        and Chandler protocol clients"""


    #Subclasses overide these constants
    accountType = AccountBase
    clientType  = "AbstractDownloadClient"
    factoryType = AbstractDownloadClientFactory
    defaultPort = 0

    def __init__(self, view, account, mailWorker):
        """
        @param view: An Instance of C{RepositoryView}
        @type view: C{RepositoryView}
        @param account: An Instance of C{DownloadAccountBase}
        @type account: C{DownloadAccount}
        @param mailWorker: An Instance of C{MailWorker}
        @type mailWorker: C{MailWorker}
        @return: C{None}
        """
        assert isinstance(account, self.accountType)
        assert isinstance(view, RepositoryView)
        assert isinstance(mailWorker, mailworker.MailWorker)

        self.view = view
        self.mailWorker = mailWorker

        #These values exist for life of client
        self.accountUUID = account.itsUUID
        self.account = None
        self.shuttingDown = False

        # Stores the total number of messages
        # downloaded during the life of the
        # client. In the IMAP example this
        # value would hold the total number
        # of messages downloaded for all
        # folders where as DownloadVars.totalDownloaded
        # would hold the total number of messages download
        # for the given folder.
        self.totalDownloaded = 0

        # These values are reassigned on each
        # connection to the server
        self.performingAction = False
        self.waitingOnCommit = False
        self.waitCallback = None
        self.testing = False
        self.logIn = True
        self.callback = None
        self.statusMessages = False
        self.factory = None
        self.proto = None
        self.reconnect = None
        self.errorHandled = False

        # Used to Log client server protocol exchanges.
        # On error if constants.DEBUG_CLIENT_SERVER = 1
        # the catchErrors method will print the values
        # in the buffer to the stdout.
        self.clientServerBuffer = None

        # Cancel is experimental and used
        # with the account testing dialog.
        # More work still needs to be done
        # for it to be useful for all protocol
        # based operations.
        self.cancel = False

        #The internal class method to
        #call after initial connection
        #to the server and login / SSL / TLS
        # is completed.
        self.cb = None

        self.vars = None

    def getMail(self):
        """Retrieves mail from a download protocol (POP, IMAP)"""
        if __debug__:
            trace("getMail")

        # Tells whether to print status messages
        self.statusMessages = True

        # Tell what method to call if the SSL acceptance
        # dialog needs to be displayed
        self.reconnect = self.getMail

        # The first callback after login / TLS /SSL
        # complete
        self.cb = self._getMail

        # Move code execution path from current thread
        # to Reactor Asynch thread
        reactor.callFromThread(self._connectToServer)

    def testAccountSettings(self, callback, reconnect, logIn=True):
        """Tests the account settings for a download protocol (POP, IMAP).
           Raises an error if unable to establish or communicate properly
           with the a server.
        """
        if __debug__:
            trace("testAccountSettings")

        # The isOnline check is performed on the Main Thread
        # so no need to pass in a view.
        if not Globals.mailService.isOnline():
            return

        assert(callback is not None)
        assert(reconnect is not None)
        assert(isinstance(logIn, bool))

        # Tells whether to print status messages
        self.statusMessages = False

        # Tell what method to call on reconnect
        # when a SSL dialog is displayed.
        # When the dialog is shown the
        # protocol code terminates the
        # connection and calls reconnect
        # if the cert has been accepted
        self.reconnect = reconnect

        # The method to call in the UI Thread
        # when the testing is complete.
        # This method is called for both success and failure.
        self.callback = callback

        # Preview timeframe addition that
        # specifies whether the protocol should
        # login the user as part of the account
        # testing. A value of True will log
        # the user in as part of the test.
        self.logIn = logIn

        # The first callback after login / TLS /SSL
        # complete
        self.cb = self._accountTestingComplete

        # Flag indicating we are in test mode
        self.testing = True

        # Move code execution path from current thread
        # to Reactor Asynch thread
        reactor.callFromThread(self._connectToServer)

    def _connectToServer(self):
        if __debug__:
            trace("_connectToServer")

        if self.cancel:
            return self._resetClient()

        self.view.refresh()

        #Overidden method
        self._getAccount()

        # The isOnline check is performed in the Twisted thread
        # so pass in a view.
        if not Globals.mailService.isOnline(self.view):
            if self.statusMessages:
                msg = constants.MAIL_PROTOCOL_OFFLINE % \
                              {"accountName": self.account.displayName}

                setStatusMessage(msg)
            return

        if self.performingAction:
            if __debug__:
                trace("%s is currently in use request ignored" % self.clientType)
            return

        self.performingAction = True

        if self.statusMessages:
            msg = constants.MAIL_PROTOCOL_CONNECTION \
                          % {"accountName": self.account.displayName,
                             "serverDNSName": self.account.host}

            setStatusMessage(msg)

        self.factory = self.factoryType(self)

        if self.testing:
            # If in testing mode then do not want to retry connection or
            # wait a long period for a timeout
            self.factory.retries = 0
            self.factory.timeout = constants.TESTING_TIMEOUT

        if self.account.connectionSecurity == 'SSL':
            ssl.connectSSL(self.account.host, self.account.port,
                           self.factory, self.view)
        else:
            ssl.connectTCP(self.account.host, self.account.port,
                           self.factory, self.view)

    def calculateCommitNumber(self):
        # Low commit numbers are used
        # till the UI has enough messages to
        # extend pass the scroll bars.
        # At that point the commit sizes
        # are increased gradually until
        # reaching the ideal number of
        # commits vs. downloaded messages
        # from a performance standpoint.
        total = self.totalDownloaded

        if total < 24:
            return 6
        elif total >= 24 and total < 100:
            return 20
        elif total >= 100 and total < 300:
            return 100
        elif total >= 300 and total < 600:
            return 200

        return constants.MAX_COMMIT

    def catchErrors(self, err):
        """
        This method captures all errors thrown while in the Twisted Reactor Thread as well
        as errors raised by non-Twisted code while in the Twisted Reactor Thread.
        catchErrors will print a stacktrace of C{failure.Failure} objects to the chandler.log.
        catchErrors also handles c{Exception}s but will not log the stacktrace to the chandler.log
        since this method is out of the scope of the original c{Exception}. The caller must log 
        its c{Exception} via the logging.exception method.

        @param err: The error thrown
        @type err: C{failure.Failure} or c{Exception}

        @return: C{None}
        """
        if __debug__:
            trace("catchErrors")


        self.waitingOnCommit = False

        if self.waitCallback is not None:
            try:
                self.waitCallback.cancel()
            except error.AlreadyCalled:
                pass

            self.waitCallback = None

        if __debug__:
            if constants.DEBUG_CLIENT_SERVER == 1 and \
                self.clientServerBuffer:
                # Prints the last four client server exchanges to
                # the stdout for debugging.
                print self.clientServerBuffer

            if constants.DEBUG_CLIENT_SERVER == 2:
                try:
                    raise err
                except Exception, err:
                    #Capture the error to the logger
                    logging.exception(err)

        if self.vars:
            # If self.vars is not None then the error
            # was raised during an Incoming Mail download.
            # In this case we want to notify the Mail Worker
            # so it can perform any cleanup that is needed.
            self.mailWorker.queueRequest((mailworker.ERROR_REQUEST,
                                          self, self.accountUUID))

        # Flag that tells the connection factory
        # that the error has been handled
        self.errorHandled = True

        # In this case don't try to clean up the transport connection
        # but do reset the client variables
        # The isOnline check is performed in the Twisted thread so
        # pass in a view.
        if self.shuttingDown or not Globals.mailService.isOnline(self.view) or \
           self.factory is None:
            self._resetClient()
            return

        # If we cancelled the request then gracefully disconnect from
        # the server and reset the client variables but do not display
        # the error.
        if self.cancel:
            return self._actionCompleted()

        if isinstance(err, failure.Failure):
            if err.check(error.ConnectionDone):
                if self.factory.retries < self.factory.sendFinished <= 0:
                    #The error processing for lost connections is in the Factory
                    #class so return here and let the Factory handle the reconnection logic.
                    return

                #set the value of the error to something more meaningful than
                #'Connection closed cleanly.'
                err.value = self.factory.exception(constants.MAIL_PROTOCOL_CONNECTION_ERROR)

            err = err.value

        if self.statusMessages:
            # Reset the status bar since the error will be displayed
            # in a dialog or handled by a callback method.
            setStatusMessage(u"")

        if isinstance(err, Utility.CertificateVerificationError):
            assert err.args[1] == 'certificate verify failed'

            # Reason why verification failed is stored in err.args[0], see
            # codes at http://www.openssl.org/docs/apps/verify.html#DIAGNOSTICS

            # Post an asynchronous event to the main thread where
            # we ask the user if they would like to trust this
            # certificate. The main thread will then initiate a retry
            # when the new certificate has been added.
            try:
                if self.callback:
                    # Send the message to destroy the progress dialog first. This needs
                    # to be done in this order on Linux because otherwise killing
                    # the progress dialog will also kill the SSL error dialog.
                    # Weird, huh? Welcome to the world of wx...
                    callMethodInUIThread(self.callback, (2, None))

                if err.args[0] in ssl.unknown_issuer:
                    d = ssl.askTrustServerCertificate(err.host, err.untrustedCertificates[0], self.reconnect)
                else:
                    d = ssl.askIgnoreSSLError(err.host,
                                              err.untrustedCertificates[0],
                                              err.args[0],
                                              self.reconnect)
                
                d.addCallback(lambda dummy: True)
                    
            except Exception, e:
                # This code should never be reached, and if it were, the _ would raise!
                log.exception('Error raised in SSL Layer which requires investigation.')
                callMethodInUIThread(self.callback, (0, _(u"SSL error.")))

            return self._actionCompleted()

        if isinstance(err, WrongHost):
            # Post an asynchronous event to the main thread where
            # we ask the user if they would like to continue even though
            # the certificate identifies a different host.

            if self.callback:
                # Send the message to destroy the progress dialog first. This needs
                # to be done in this order on Linux because otherwise killing
                # the progress dialog will also kill the SSL error dialog.
                # Weird, huh? Welcome to the world of wx...
                callMethodInUIThread(self.callback, (2, None))

            d = ssl.askIgnoreSSLError(err.expectedHost,
                                      err.pem,
                                      messages.SSL_HOST_MISMATCH % \
                                        {'actualHost': err.actualHost},
                                      self.reconnect)

            d.addCallback(lambda dummy: True)

            return self._actionCompleted()

        errorText = unicode(err.__str__(), 'utf8', 'ignore')

        if self.callback:
            callMethodInUIThread(self.callback, (0, errorText))
        else:
            if isinstance(err, errors.IMAPTimeoutException):
                alertMailError(constants.MAIL_PROTOCOL_TIMEOUT_ERROR, self.account,
                               {'hostName': self.account.host},
                               constants.MAIL_PROTOCOL_TROUBLESHOOT)
            else:
                alertMailError(constants.MAIL_PROTOCOL_ERROR, self.account,
                               {'hostName': self.account.host, 'errText': errorText})

        self._actionCompleted()

        return None

    def loginClient(self):
        """
        Called after serverGreeting to log in a client to the server via
        a protocol (IMAP, POP)

        @return: C{None}
        """
        if __debug__:
            trace("loginClient")

        if self.cancel:
            return self._actionCompleted()

        if not self.logIn:
            callMethodInUIThread(self.callback, (1, None))
            return self._actionCompleted()

        self._loginClient()


    def requestsComplete(self):
        if __debug__:
            trace("requestsComplete")
        # Callback from the MailWorker thread notifying that
        # the request actions are complete.
        # The client needs to block (ie. not perform any new actions)
        # until the MailWoker has complete all requests from the client
        # and processed the clients DONE_REQUEST.
        self.performingAction = False


    def cancelLastRequest(self):
        if __debug__:
            trace("cancelLastRequest")

        if self.performingAction or self.testing:
            self.cancel = True

    def shutdown(self):
        if __debug__:
            trace("shutdown")

        self.shuttingDown = True


    def _accountTestingComplete(self, results):
        if not self.cancel:
            callMethodInUIThread(self.callback, (1, None))

        return self._actionCompleted()

    def _beforeDisconnect(self):
        """Overide this method to place any protocol specific
           logic to be handled before disconnect i.e. send a 'Quit'
           command.
        """
        if __debug__:
            trace("_beforeDisconnect")

        return defer.succeed(True)

    def _disconnect(self, result=None):
        """Disconnects a client from a server.
           Has logic to make sure that the client is actually
           connected.
        """
        if __debug__:
            trace("_disconnect")

        if not self.factory:
            return

        self.factory.sendFinished = 1

        if not self.factory.connectionLost and self.proto:
            self.proto.transport.loseConnection()

    def _actionCompleted(self, releaseLock=True):
        """Handles clean up after mail downloaded
           by calling:
               1. _beforeDisconnect
               2. _disconnect
               3. _resetClient
        """
        if __debug__:
            trace("_actionCompleted")

        d = self._beforeDisconnect()
        d.addBoth(self._disconnect)
        d.addBoth(lambda _: self._resetClient(releaseLock))
        return d

    def _resetClient(self, releaseLock=True):
        """Resets Client object state variables to
           default state.
        """
        if __debug__:
            trace("_resetClient")

        # Release the performingAction lock
        if releaseLock:
            self.performingAction = False

        self.waitingOnCommit = False
        self.waitCallback = None

        # Reset testing to False
        self.testing = False

        # Reset logIn to True

        self.logIn = True

        # Reset callback to None
        self.callback = None

        # Reset the cancel flag
        self.cancel = False

        #reset the show status messages flag
        self.statusMessages = False

        # Reset the debug protocol buffer
        self.clientServerBuffer = None

        self.totalDownloaded = 0

        # Clear out per request values
        self.factory         = None
        self.cb              = None
        self.reconnect       = None
        self.proto           = None
        self.errorHandled    = False
        self.vars            = None


    def _commitMail(self, statusMessage=None, protocolArgs=None):
        if __debug__:
            trace("_commitMail")

        self.mailWorker.queueRequest((mailworker.MAIL_REQUEST, 
                                      self,
                                      self.accountUUID,
                                      self.vars.messages,
                                      statusMessage,
                                      protocolArgs))

        if constants.WAIT_FOR_COMMIT:
            self.waitingOnCommit = True
            self.waitCallback = reactor.callLater(constants.NOOP_INTERVAL, 
                                                  self._sendNoop)
        else:
            self.nextAction()


    def _sendNoop(self):
        if __debug__:
            trace("_sendNoop")
        if self.waitingOnCommit:
            self.proto.noop()
            self.waitCallback = reactor.callLater(constants.NOOP_INTERVAL,
                                                  self._sendNoop)

        return None

    def _getAccount(self):
        """Overide this method to add custom account
           look up logic. Accounts can not be passed across
           threads so the C{UUID} must be used to fetch the
           account's data
        """
        if self.account is None:
            self.account = self.view.findUUID(self.accountUUID)

        return self.account

    def _getNextMessageSet(self):
        """Overide this to add retrieval of
           message set logic for POP. IMAP, etc
        """
        raise NotImplementedError()

    def _loginClient(self):
        """Overide this method to place any protocol specific
           logic to be handle logging in to client
        """

        raise NotImplementedError()

    def _getMail(self, result):
        """Overide this method to place any protocol specific
           logic to be handled after the client has logged.
        """
        raise NotImplementedError()

    def nextAction(self):
        raise NotImplementedError()

    def _nextAction(self):
        if __debug__:
            trace("_nextAction")

        self.waitingOnCommit = False

        if self.waitCallback is not None:
            try:
                self.waitCallback.cancel()
            except error.AlreadyCalled:
                pass

            self.waitCallback = None

        self.vars.numDownloaded = 0
        self.vars.numToDownload = 0

        self.vars.messages = []

    def _saveToBuffer(self, txt):
        if self.clientServerBuffer is None:
            self.clientServerBuffer = []

        self.clientServerBuffer.append(txt)

        if len(self.clientServerBuffer) >= 5:
            # Get rid of the last command
            self.clientServerBuffer.pop(0)

    def _getStatusStats(self):
        return {
               "accountName": self.account.displayName,
                "start": self.vars.totalDownloaded,
                "end": self.vars.totalDownloaded + \
                       len(self.vars.messages),
                "total": self.vars.totalToDownload,
               }
