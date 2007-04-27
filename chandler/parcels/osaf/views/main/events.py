#   Copyright (c) 2003-2007 Open Source Applications Foundation
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


from osaf.framework.blocks import (
    AddToSidebarEvent, BlockEvent, NewItemEvent, NewBlockWindowEvent,
    ClassParameterizedEvent, ChoiceEvent, ViewEvent)
from osaf.framework.blocks.calendar import CalendarViewEvent


def makeMainEvents(parcel):

    from application import schema
    import osaf.pim.notes
    import osaf.pim.calendar
    import osaf.pim.mail
    import osaf.pim.tasks
    from osaf import pim, messages

    repositoryView = parcel.itsView

    # NewItemEvent's commitAfterDispatch defaults to True
    NewItemEvent.update(parcel, 'NewItem',
                        blockName = 'NewItem')

    NewItemEvent.update(parcel, 'NewNote',
                        blockName = 'NewNote',
                        classParameter = osaf.pim.notes.Note)

    NewItemEvent.update(parcel, 'NewMailMessage',
                        blockName = 'NewMailMessage',
                        classParameter = osaf.pim.mail.MailStamp)

    NewItemEvent.update(parcel, 'NewCalendar',
                        blockName = 'NewCalendar',
                        classParameter = osaf.pim.calendar.Calendar.EventStamp)

    NewItemEvent.update(parcel, 'NewTask',
                        blockName = 'NewTask',
                        classParameter = osaf.pim.tasks.TaskStamp)

    BlockEvent.template('ReminderTime',
                        dispatchEnum = 'SendToBlockByReference'
                        # destinatinBlockReference is assigned in makeMakeView
                        # because of a circular dependence
                        ).install(parcel)
    
    BlockEvent.template('RunSelectedScript',
                        dispatchEnum = 'FocusBubbleUp',
                        commitAfterDispatch = True).install(parcel)

    # Event to put "Scripts" in the Sidebar
    BlockEvent.template('AddScriptsToSidebar',
                        commitAfterDispatch = True).install(parcel)

    BlockEvent.template('AddSharingLogToSidebar',
                        commitAfterDispatch = True).install(parcel)

    BlockEvent.template('CalDAVAtopEIM',
                        commitAfterDispatch = True).install(parcel)

    BlockEvent.template('RecordSetDebugging',
        commitAfterDispatch = True).install(parcel)

    BlockEvent.template('InmemoryPublish',
        commitAfterDispatch = True).install(parcel)

    BlockEvent.template('SwitchRepository').install(parcel)

    BlockEvent.template('CreateRepository').install(parcel),

    BlockEvent.template('CompactRepository').install(parcel)

    BlockEvent.template('IndexRepository').install(parcel)

    BlockEvent.template('UnpublishCollection',
                        commitAfterDispatch = True).install(parcel)

    BlockEvent.template('UnsubscribeCollection',
                        commitAfterDispatch = True).install(parcel)

    BlockEvent.template('SharingPublishFreeBusy',
                        commitAfterDispatch = True).install(parcel)

    BlockEvent.template('SharingUnpublishFreeBusy',
                        commitAfterDispatch = True).install(parcel)

    BlockEvent.template('CopyFreeBusyURL').install(parcel)

    BlockEvent.template('ShowPyCrust').install(parcel)

    BlockEvent.template('ShowHideStatusBar',
                        methodName = 'onShowHideEvent',
                        dispatchToBlockName = 'StatusBar').install(parcel)

    BlockEvent.template('EnableTimezones',
                        commitAfterDispatch = True).install(parcel)

    # "Test" menu event
    BlockEvent.template('CreateConflict',
                        dispatchEnum = 'FocusBubbleUp',
                        commitAfterDispatch = True).install(parcel)

    # "Item" menu events
    BlockEvent.template('FocusTogglePrivate',
                        dispatchEnum = 'FocusBubbleUp',
                        commitAfterDispatch = True).install(parcel)

    ClassParameterizedEvent.template('FocusStampMessage',
                                     methodName = 'onFocusStampEvent',
                                     classParameter = osaf.pim.mail.MailStamp,
                                     dispatchEnum = 'FocusBubbleUp',
                                     commitAfterDispatch = True).install(parcel)

    ClassParameterizedEvent.template('FocusStampTask',
                                     methodName = 'onFocusStampEvent',
                                     classParameter = osaf.pim.tasks.TaskStamp,
                                     dispatchEnum = 'FocusBubbleUp',
                                     commitAfterDispatch = True).install(parcel)

    ClassParameterizedEvent.template('FocusStampCalendar',
                                     methodName = 'onFocusStampEvent',
                                     classParameter = osaf.pim.calendar.Calendar.EventStamp,
                                     dispatchEnum = 'FocusBubbleUp',
                                     commitAfterDispatch = True).install(parcel)

    ClassParameterizedEvent.template('ReplyMessage',
                                     methodName = 'onReplyEvent',
                                     classParameter = osaf.pim.mail.MailStamp,
                                     dispatchEnum = 'FocusBubbleUp',
                                     commitAfterDispatch = True).install(parcel)

    ClassParameterizedEvent.template('ReplyAllMessage',
                                     methodName = 'onReplyAllEvent',
                                     classParameter = osaf.pim.mail.MailStamp,
                                     dispatchEnum = 'FocusBubbleUp',
                                     commitAfterDispatch = True).install(parcel)

    ClassParameterizedEvent.template('ForwardMessage',
                                     methodName = 'onForwardEvent',
                                     classParameter = osaf.pim.mail.MailStamp,
                                     dispatchEnum = 'FocusBubbleUp',
                                     commitAfterDispatch = True).install(parcel)

    BlockEvent.template('SubscribeToCollection',
                        commitAfterDispatch = True).install(parcel)

    BlockEvent.template('CheckRepository').install(parcel)

    BlockEvent.template('CheckAndRepairRepository').install(parcel)

    BlockEvent.template('i18nMailTest',
                        commitAfterDispatch = True).install(parcel)

    BlockEvent.template('ShowI18nManagerDebugWindow').install(parcel)

    BlockEvent.template('ShowMeAddressCollectionDebugWindow').install(parcel)
    
    BlockEvent.template('ShowCurrentMeAddressesDebugWindow').install(parcel)

    BlockEvent.template('ShowCurrentMeAddressDebugWindow').install(parcel)

    BlockEvent.template('RecalculateMeAddresses',
                        commitAfterDispatch = True).install(parcel)

    BlockEvent.template('ShowLogWindow').install(parcel)

    BlockEvent.template('ActivateWebserver').install(parcel)

    BlockEvent.template('ShowActivityViewer').install(parcel)

    BlockEvent.template('BackgroundSyncAll').install(parcel)

    BlockEvent.template('BackgroundSyncGetOnly').install(parcel)

    BlockEvent.template('ToggleReadOnlyMode',
                        commitAfterDispatch = True).install(parcel)

    BlockEvent.template('EditMyName',
                        commitAfterDispatch = True).install(parcel)

    BlockEvent.template('GetNewMail',
                        commitAfterDispatch = True).install(parcel)

    BlockEvent.template('ManageSidebarCollection').install(parcel)

    BlockEvent.template('ShowPyShell').install(parcel)

    BlockEvent.template('SaveSettings').install(parcel)

    BlockEvent.template('RestoreSettings',
                        commitAfterDispatch = True).install(parcel)

    BlockEvent.template('EditAccountPreferences').install(parcel)

    BlockEvent.template('ProtectPasswords',
                        commitAfterDispatch = True).install(parcel)

    BlockEvent.template('ShowHideSidebar',
                        methodName = 'onShowHideEvent',
                        dispatchToBlockName = 'SidebarContainer').install(parcel)

    BlockEvent.template('ReloadStyles',
                        dispatchEnum = 'SendToBlockByName',
                        dispatchToBlockName = 'MainView',
                        commitAfterDispatch = True).install(parcel)

    BlockEvent.template('Triage',
                        commitAfterDispatch = True,
                        dispatchEnum = 'SendToBlockByName',
                        dispatchToBlockName = 'DashboardSummaryView',
                        commitAfterDispatch = True).install(parcel)

    ClassParameterizedEvent.template('ApplicationBarAll',
                                     methodName = 'onClassParameterizedEvent',
                                     dispatchToBlockName = 'Sidebar').install(parcel)

    ClassParameterizedEvent.template('ApplicationBarMail',
                                     methodName = 'onClassParameterizedEvent',
                                     classParameter = osaf.pim.mail.MailStamp,
                                     dispatchToBlockName = 'Sidebar').install(parcel)

    ClassParameterizedEvent.template('ApplicationBarEvent',
                                     methodName = 'onClassParameterizedEvent',
                                     classParameter = osaf.pim.calendar.Calendar.EventStamp,
                                     dispatchToBlockName = 'Sidebar').install(parcel)

    ClassParameterizedEvent.template('ApplicationBarTask',
                                     methodName = 'onClassParameterizedEvent',
                                     classParameter = osaf.pim.tasks.TaskStamp,
                                     dispatchToBlockName = 'Sidebar').install(parcel)

    BlockEvent.template('PublishCollection').install(parcel)

    BlockEvent.template('SetLoggingLevelCritical').install(parcel)

    BlockEvent.template('SetLoggingLevelError').install(parcel)

    BlockEvent.template('SetLoggingLevelWarning').install(parcel)

    BlockEvent.template('SetLoggingLevelInfo').install(parcel)

    BlockEvent.template('SetLoggingLevelDebug').install(parcel)

    BlockEvent.template('RestoreShares').install(parcel)

    BlockEvent.template('SyncPrefs').install(parcel)

    BlockEvent.template('SyncCollection').install(parcel)

    BlockEvent.template('ToggleMine',
                        dispatchToBlockName = 'Sidebar',
                        commitAfterDispatch = True).install(parcel)

    BlockEvent.template('DumpToFile').install(parcel)

    BlockEvent.template('ObfuscatedDumpToFile').install(parcel)

    BlockEvent.template('ReloadFromFile',
                        commitAfterDispatch = True).install(parcel)

    BlockEvent.template('ShowHideApplicationBar',
                        methodName = 'onShowHideEvent',
                        dispatchToBlockName = 'ApplicationBar').install(parcel)

    BlockEvent.template('GenerateContentItems',
                        commitAfterDispatch = True).install(parcel)

    ChoiceEvent.template('ChooseChandlerMainView',
                         methodName = 'onChoiceEvent',
                         choice = 'MainView',
                         dispatchToBlockName = 'MainViewRoot').install(parcel)

    BlockEvent.template('ExportIcalendar').install(parcel)

    BlockEvent.template('SyncAll').install(parcel)

    untitledCollection = pim.SmartCollection.update(parcel,
                                                    'untitledCollection',
                                                    displayName=messages.UNTITLED)

    AddToSidebarEvent.update(
        parcel, 'NewCollection',
        blockName = 'NewCollection',
        editAttributeNamed = 'displayName',
        sphereCollection = schema.ns('osaf.pim', repositoryView).mine,
        item = untitledCollection)
        
    BlockEvent.template('GenerateContentItemsFromFile',
                        commitAfterDispatch = True).install(parcel)

    BlockEvent.template('EmptyTrash',
                        commitAfterDispatch = True).install(parcel)

    BlockEvent.template('MimeTest',
                        commitAfterDispatch = True).install(parcel)

    BlockEvent.template('SyncWebDAV').install(parcel)

    BlockEvent.template('WxTestHarness').install(parcel)

    BlockEvent.template('ImportIcalendar',
                       commitAfterDispatch = True).install(parcel)

    BlockEvent.template('CopyCollectionURL').install(parcel)

    BlockEvent.template('TakeOnlineOffline',
                       commitAfterDispatch = True).install(parcel)

    BlockEvent.template('TakeAllOnlineOffline').install(parcel)
    
    BlockEvent.template('TakeMailOnlineOffline').install(parcel)

    BlockEvent.template('TakeSharesOnlineOffline').install(parcel)

    ChoiceEvent.template('ChooseCPIATestMainView',
                         methodName = 'onChoiceEvent',
                         choice = 'CPIATestMainView',
                         dispatchToBlockName = 'MainViewRoot').install(parcel)

    ChoiceEvent.template('ChooseCPIATest2MainView',
                         methodName = 'onChoiceEvent',
                         choice = 'CPIATest2MainView',
                         dispatchToBlockName = 'MainViewRoot').install(parcel)

    BlockEvent.template('RequestSelectSidebarItem',
                        dispatchToBlockName = 'Sidebar').install(parcel)
    
    BlockEvent.template('SendMail',
                       commitAfterDispatch = True).install(parcel)

    BlockEvent.template('QuickEntry',
                        dispatchEnum = 'FocusBubbleUp').install(parcel)

    BlockEvent.template('Search',
                        commitAfterDispatch = True,
                        dispatchEnum = 'FocusBubbleUp').install(parcel)

    BlockEvent.template('SendShareItem',
                        commitAfterDispatch = True,
                        dispatchEnum = 'FocusBubbleUp').install(parcel)

    BlockEvent.template('ShareItem',
                        commitAfterDispatch = True).install(parcel)
                  
    BlockEvent.template('SelectedDateChanged',
                        dispatchEnum = 'BroadcastEverywhere').install(parcel)
    
    BlockEvent.template('DayMode',
                        dispatchEnum = 'BroadcastEverywhere').install(parcel)
        
    blockViewer = schema.ns("osaf.views.blockviewer", repositoryView)
    
    NewBlockWindowEvent.update(parcel, 'ShowBlockViewer',
                               blockName = 'ShowBlockViewer',
                               treeOfBlocks = blockViewer.BlockViewerFrameWindow)

    repositoryViewer = schema.ns("osaf.views.repositoryviewer", repositoryView)

    NewBlockWindowEvent.update(parcel, 'ShowRepositoryViewer',
                               blockName = 'ShowBlockViewer',
                               treeOfBlocks = repositoryViewer.RepositoryViewerFrameWindow)

    CalendarViewEvent.template('ViewAsDayCalendar',
                               viewTemplatePath = 'osaf.views.main.CalendarSummaryViewTemplate',
                               methodName = 'onViewEvent',
                               dayMode = True,
                               dispatchToBlockName = 'SidebarBranchPointBlock').install(parcel)

    CalendarViewEvent.template('ViewAsWeekCalendar',
                               viewTemplatePath = 'osaf.views.main.CalendarSummaryViewTemplate',
                               methodName = 'onViewEvent',
                               dayMode = False,
                               dispatchToBlockName = 'SidebarBranchPointBlock').install(parcel)

    ViewEvent.template('ViewAsDashboard',
                       viewTemplatePath = 'osaf.views.main.DashboardSummaryViewTemplate',
                       methodName = 'onViewEvent',
                       dispatchToBlockName = 'SidebarBranchPointBlock').install(parcel)

    BlockEvent.template('DuplicateSidebarSelection',
                        methodName = 'onDuplicateEvent',
                        dispatchToBlockName = 'Sidebar',
                        commitAfterDispatch = True).install(parcel)

    BlockEvent.template('RenameCollection',
                        methodName = 'onRenameEvent',
                        dispatchToBlockName = 'Sidebar',
                        commitAfterDispatch = True).install(parcel),
    
    BlockEvent.template('DeleteCollection',
                        methodName = 'onDeleteEvent',
                        dispatchToBlockName = 'Sidebar',
                        commitAfterDispatch = True).install(parcel),

    BlockEvent.template('DeleteInActiveView',
                        methodName = 'onDeleteEvent',
                        dispatchEnum = 'ActiveViewBubbleUp',
                        commitAfterDispatch = True).install(parcel)

    BlockEvent.template('RemoveInActiveView',
                        dispatchEnum = 'ActiveViewBubbleUp',
                        methodName = 'onRemoveEvent',
                        commitAfterDispatch = True).install(parcel),

    BlockEvent.template('CutInActiveView',
                        dispatchEnum = 'ActiveViewBubbleUp',
                        methodName = 'onCutEvent',
                        commitAfterDispatch = True).install(parcel),

    BlockEvent.template('CopyInActiveView',
                        dispatchEnum = 'ActiveViewBubbleUp',
                        methodName = 'onCopyEvent',
                        commitAfterDispatch = True).install(parcel),

    BlockEvent.template('DuplicateInActiveView',
                        dispatchEnum = 'ActiveViewBubbleUp',
                        methodName = 'onDuplicateEvent',
                        commitAfterDispatch = True).install(parcel),

    BlockEvent.template('PasteInActiveView',
                        dispatchEnum = 'ActiveViewBubbleUp',
                        methodName = 'onPasteEvent',
                        commitAfterDispatch = True).install(parcel),

