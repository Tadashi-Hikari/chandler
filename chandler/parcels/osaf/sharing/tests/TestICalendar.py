#   Copyright (c) 2003-2008 Open Source Applications Foundation
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

"""
A helper class which sets up and tears down dual RamDB repositories
"""

import unittest, os
from util.testcase import SharedSandboxTestCase, NRVTestCase
import chandlerdb.persistence.DBRepository as DBRepository
import chandlerdb.item.Item as Item
import application.Parcel as Parcel
from application import schema
from osaf import pim, sharing
import osaf.sharing.ICalendar as ICalendar
from osaf.sharing.serialize import serialize, deserialize
from osaf.sharing import ics, translator
from osaf.pim import ListCollection, Note, Triageable
import osaf.pim.calendar.Calendar as Calendar
from osaf.pim.calendar.TimeZone import (convertToICUtzinfo, TimeZoneInfo,
                                        equivalentTZIDs)
import datetime
import vobject
import cStringIO
from PyICU import ICUtzinfo, FloatingTZ
from dateutil import tz
from osaf.pim.calendar.Recurrence import (RecurrenceRule, RecurrenceRuleSet,
                                          WeekdayAndPositionStruct)
from i18n.tests import uw

def getVObjectData(view, events):
    text = serialize(view, events, translator.SharingTranslator,
                     ics.ICSSerializer)
    return vobject.readOne(text)

class ICalendarTestCase(SharedSandboxTestCase):

    def setUp(self):
        super(ICalendarTestCase, self).setUp()
        
        self.utc = self.view.tzinfo.getInstance('utc')

    def Import(self, view, filename):
        path = self.getTestResourcePath(filename)
        self.importedCollection = sharing.importFile(view, path)

    def testMidnightToMidnight(self):
        """
        When importing iCalendar data, treat floating midnight-to-midnight
        events as all-day, bug 9579.
        """        
        self.Import(self.view, u'MidnightToMidnight.ics')
        event = pim.EventStamp(sharing.findUID(self.view, 'midnight'))
        endTime = datetime.datetime(2007,6,20)
        self.assert_(event.effectiveEndTime.replace(tzinfo=None) == endTime)
        self.assert_(event.allDay == True)

    def testNoMaster(self):
        """
        Treat a modification without a master as a normal event, because Google
        exports events like this, bug 10821.
        """        
        self.Import(self.view, u'NoMaster.ics')
        event = pim.EventStamp(sharing.findUID(self.view, 'no_master'))
        rruleset = getattr(event, 'rruleset', None)
        self.assertEqual(rruleset, None)

    def testSummaryAndDateTimeImported(self):
        self.Import(self.view, u'Chandler.ics')
        event = pim.EventStamp(sharing.findUID(
                                    self.view,
                                   'BED962E5-6042-11D9-BE74-000A95BB2738'))
        self.assertEqual(event.summary, u'3 ho\u00FCr event',
                 u"SUMMARY of first VEVENT not imported correctly, displayName is %s"
                 % event.summary)
        evtime = datetime.datetime(2005,1,1, hour = 23, tzinfo = self.utc)
        self.assert_(event.startTime == evtime,
         "startTime not set properly, startTime is %s"
         % event.startTime)

    def testDateImportAsAllDay(self):
        self.Import(self.view, u'AllDay.ics')
        event = pim.EventStamp(sharing.findUID(self.view, 'testAllDay'))
        self.failUnless(pim.has_stamp(event, pim.EventStamp))
        self.assert_(event.startTime ==
                     datetime.datetime(2005,1,1, tzinfo=self.view.tzinfo.floating),
         "startTime not set properly for all day event, startTime is %s"
         % event.startTime)
        self.assert_(event.allDay == True,
         "allDay not set properly for all day event, allDay is %s"
         % event.allDay)

    def testRDateOnly(self):
        self.Import(self.view, u'rdates.ics')
        event = pim.EventStamp(sharing.findUID(self.view, 'rdate_test'))
        self.failUnless(pim.has_stamp(event, pim.EventStamp))
        self.assertEqual(len(event.rruleset.rdates), 3)

    def testDateValuedExDate(self):
        self.Import(self.view, u'AllDayRecurrence.ics')
        event = pim.EventStamp(sharing.findUID(self.view, 'testAllDay'))
        self.assertEqual(len(event.rruleset.exdates), 2)
        self.assertEqual(
            event.rruleset.exdates[0],
            datetime.datetime(2007, 10, 15, 0, 0, tzinfo=self.view.tzinfo.floating)
        )
        self.assertEqual(
            event.rruleset.exdates[1],
            datetime.datetime(2007, 10, 29, 0, 0, tzinfo=self.view.tzinfo.floating)
        )
         

    def testExportFreeBusy(self):
        self.Import(self.view, u'AllDay.ics')
        schema.ns('osaf.pim', self.view).mine.addSource(self.importedCollection)

        start = datetime.datetime(2005,1,1, tzinfo=self.view.tzinfo.floating)
        end = start + datetime.timedelta(2)

        cal = ICalendar.itemsToFreeBusy(self.view, start, end)
        busy_start, busy_end = cal.vfreebusy.freebusy.value[0]
        self.assertEqual(busy_end - busy_start, datetime.timedelta(1))

    def testICSSerializer(self):
        """Tests serialization of items to icalendar streams."""
        event = Calendar.CalendarEvent(itsView = self.view)
        event.anyTime = False
        event.summary = uw("test")
        event.startTime = datetime.datetime(2010, 1, 1, 10,
                                            tzinfo=self.view.tzinfo.default)
        event.endTime = datetime.datetime(2010, 1, 1, 11,
                                          tzinfo=self.view.tzinfo.default)
        
        cal = getVObjectData(self.view, [event.itsItem])

        self.failUnlessEqual(cal.vevent.summary.value, uw("test"),
         u"summary not set properly, summary is %s"
         % cal.vevent.summary.value)

        start = event.startTime
        self.assert_(cal.vevent.dtstart.value == start,
         "dtstart not set properly, dtstart is %s"
         % cal.vevent.summary.value)

        event = Calendar.CalendarEvent(itsView = self.view)
        event.summary = uw("test2")
        event.startTime = datetime.datetime(2010, 1, 1, 
                                            tzinfo=self.view.tzinfo.floating)
        event.allDay = True
        event.duration = datetime.timedelta(1)
        self.assertEqual(event.effectiveEndTime - event.effectiveStartTime,
                         datetime.timedelta(2))
        cal = getVObjectData(self.view, [event.itsItem])

        self.assert_(cal.vevent.dtstart.value == datetime.date(2010,1,1),
         u"dtstart for allDay event not set properly, dtstart is %s"
         % cal.vevent.summary.value)
        
        # test bug 9137, multi-day all-day events with
        # duration modulo 1 day == 0 are serialized as 1 day instead of 2
        self.assertEqual(cal.vevent.duration.value, datetime.timedelta(2))
        # test bug 3509, all day event duration is off by one

    def testWriteICalendarUnicodeBug3338(self):
        event = Calendar.CalendarEvent(itsView = self.view)
        event.summary = u"unicode \u0633\u0644\u0627\u0645"
        event.startTime = datetime.datetime(2010, 1, 1, 10,
                                            tzinfo=self.view.tzinfo.default)
        event.endTime = datetime.datetime(2010, 1, 1, 11,
                                          tzinfo=self.view.tzinfo.default)
        event.rruleset = self._makeRecurrenceRuleSet()

        coll = ListCollection("testcollection", itsParent=self.sandbox)
        coll.displayName = "test"
        coll.add(event.itsItem)
        # the view needs to be committed for event to be seen by sync
        self.view.commit() 
        
        filename = u"unicode_export.ics"

        def delFile():
            try:
                os.remove(filename)
            except OSError:
                pass
        
        delFile()
        sharing.exportFile(self.view, os.path.join(".", filename), coll)
        
        cal = vobject.readComponents(file(filename, 'rb')).next()
        self.assertEqual(cal.vevent.summary.value, event.summary)
        # no modifications should be serialized
        self.assertEqual(len(cal.vevent_list), 1)
        delFile()
        
    def doRoundTripRecurrenceCountTest(self, tzName):
        from osaf.pim.calendar.TimeZone import TimeZoneInfo
        
        tzinfo = TimeZoneInfo.get(self.view)
        tzPrefs = schema.ns('osaf.pim', self.view).TimezonePrefs
        
        saveTz = tzinfo.default
        saveShowUI = tzPrefs.showUI
        
        tzinfo.default = self.view.tzinfo.getInstance(tzName)
        
        try:
        
            self.Import(self.view, u'Recurrence.ics')
            event = pim.EventStamp(sharing.findUID(self.view,
                                        '5B30A574-02A3-11DA-AA66-000A95DA3228'))
            third = event.getFirstOccurrence().getNextOccurrence().getNextOccurrence()
            self.assertEqual(third.summary, u'\u00FCChanged title')
            self.assertEqual(
                third.recurrenceID,
                datetime.datetime(2005, 8, 10, tzinfo=self.view.tzinfo.floating)
            )
            # while were at it, test bug 3509, all day event duration is off by one
            self.assertEqual(event.duration, datetime.timedelta(0))
            # make sure we imported the floating EXDATE
            event = pim.EventStamp(sharing.findUID(self.view,
                                        '07f3d6f0-4c04-11da-b671-0013ce40e90f'))
            self.assertEqual(
                event.rruleset.exdates[0],
                datetime.datetime(2005, 12, 6, 12, 30, tzinfo=self.view.tzinfo.floating)
            )
            
            # test count export, no timezones
            vcalendar = getVObjectData(self.view, [event.itsItem])
            self.assertEqual(vcalendar.vevent.rruleset._rrule[0]._count, 10)
    
            # turn on timezones, putting event in Pacific time
            pacific = self.view.tzinfo.getInstance("America/Los_Angeles")
            TimeZoneInfo.get(self.view).default = pacific
            schema.ns('osaf.pim', self.view).TimezonePrefs.showUI = True
            self.assertEqual(event.startTime.tzinfo, pacific)
            
            # test count export, with timezones turned on
            vcalendar = getVObjectData(self.view, [event.itsItem])
            self.assertEqual(vcalendar.vevent.rruleset._rrule[0]._count, 10)
            
        finally:
            # Restore global settings
            tzPrefs.showUI = saveShowUI
            tzinfo.default = saveTz

    def testRoundTripRecurrenceCount_America_New_York(self):
        self.doRoundTripRecurrenceCountTest("America/New_York")
        
    def testRoundTripRecurrenceCount_America_El_Lay(self):
        self.doRoundTripRecurrenceCountTest("America/Los_Angeles")

    def testRoundTripRecurrenceCount_Antarctica_Vostok(self):
        """March, little Penguins, march!"""
        self.doRoundTripRecurrenceCountTest("Antarctica/Vostok")


    def testImportRecurrenceWithTimezone(self):
        self.Import(self.view, u'RecurrenceWithTimezone.ics')
        event = pim.EventStamp(sharing.findUID(self.view,
                                  'FF14A660-02A3-11DA-AA66-000A95DA3228'))
        mods = [evt for evt in event.modifications if
                not pim.EventStamp(evt).isTriageOnlyModification()]
        # The old ICalendar import code would handle THISANDFUTURE changes by
        # creating a new series, so there would be no modifications to the
        # original.  The current code just ignores THISANDFUTURE changes,
        # so there should still be no modifications
        self.assertEqual(len(mods), 0)
        # Bug 6994, EXDATEs need to have ICU timezones, or they won't commit
        # (unless we're suffering from Bug 7023, in which case tzinfos are
        # changed silently, often to GMT, without raising an exception)
        self.assertEqual(event.rruleset.exdates[0].tzinfo,
                         self.view.tzinfo.getInstance('US/Central'))

    def testImportRecurrenceAndTriageStatus(self):
        self.Import(self.view, u'Recurrence.ics')
        event = pim.EventStamp(sharing.findUID(self.view,
                                  '5B30A574-02A3-11DA-AA66-000A95DA3228'))

        # test triage of imported recurring event: Bug 9414, there should be a
        # modification for the master triaged DONE in the DONE section.
        # Doing an updateTriageStatus should cause that modification to go
        # away
        firstOccurrence = event.getFirstOccurrence()
        self.assertEqual(firstOccurrence.modificationFor, event.itsItem)
        ts = firstOccurrence.itsItem._triageStatus
        sts = getattr(firstOccurrence.itsItem, '_sectionTriageStatus', ts)

        self.assertEqual(ts, pim.TriageEnum.done)
        self.assertEqual(sts, pim.TriageEnum.done)
        
        event.updateTriageStatus()
        self.assertEqual(firstOccurrence.modificationFor, None)
        self.assertEqual(firstOccurrence.itsItem._triageStatus,
                         pim.TriageEnum.done)
        sts = getattr(firstOccurrence.itsItem, '_sectionTriageStatus', None)
        self.assertEqual(sts, None)
        

    def testImportUnusualTzid(self):
        self.Import(self.view, u'UnusualTzid.ics')
        event = pim.EventStamp(sharing.findUID(
                                self.view,
                                '42583280-8164-11da-c77c-0011246e17f0'))
        mountain_time = self.view.tzinfo.getInstance('America/Denver')
        self.assertEqual(event.startTime.tzinfo, mountain_time)

    def testWeekdayEvent(self):
        self.Import(self.view, 'WeekdayEvent.ics')
        event = pim.EventStamp(sharing.findUID(
                                self.view,
                                '5fc9f9a2-0655-11dd-8f5a-0016cbca6aed'))
        rruleset = event.rruleset
        self.failUnless(rruleset is not None)
        self.failUnlessEqual(len(list(rruleset.rrules)), 1)

        rrule = rruleset.rrules.first()
        self.failUnlessEqual(rrule.freq, 'weekly')
        self.failUnlessEqual(rrule.interval, 1)
        self.failUnlessEqual(
            [(ws.weekday, ws.selector) for ws in rrule.byweekday],
            [
                ('monday', 0), ('tuesday', 0), ('wednesday', 0),
                ('thursday', 0), ('friday', 0)
            ]
        )
        self.failUnless(rrule.isWeekdayRule())

    def testImportReminders(self):
        # @@@ [grant] Check for that reminders end up expired or not, as
        # appropriate.
        self.Import(self.view, u'RecurrenceWithAlarm.ics')
        future = pim.EventStamp(sharing.findUID(self.view,
                                'RecurringAlarmFuture'))
        reminder = future.itsItem.getUserReminder()
        # this will start failing in 2015...
        self.assertEqual(reminder.delta, datetime.timedelta(minutes=-5))
        second = future.getFirstOccurrence().getNextOccurrence()
        self.failUnless(second.itsItem.reminders is future.itsItem.reminders)

        past = pim.EventStamp(sharing.findUID(self.view, 'RecurringAlarmPast'))
        reminder = past.itsItem.getUserReminder()
        self.assertEqual(reminder.delta, datetime.timedelta(hours=-1))
        second = past.getFirstOccurrence().getNextOccurrence()
        self.failUnless(second.itsItem.reminders is past.itsItem.reminders)

    def testImportAbsoluteReminder(self):
        self.Import(self.view, u'AbsoluteReminder.ics')
        eventItem = sharing.findUID(self.view, 'I-have-an-absolute-reminder')
        reminder = eventItem.getUserReminder()
        self.failUnless(reminder is not None, "No reminder was set")
        self.failUnlessEqual(reminder.absoluteTime,
                             datetime.datetime(2006, 9, 25, 8,
                                    tzinfo=self.view.tzinfo.getInstance('America/Los_Angeles')))

    def _makeRecurrenceRuleSet(self, until=None, freq='daily', byweekday=None):
        ruleItem = RecurrenceRule(None, itsView=self.view)
        ruleItem.freq = freq
        if byweekday is not None:
            ruleItem.byweekday = byweekday
        if until is not None:
            ruleItem.until = until
        ruleSetItem = RecurrenceRuleSet(None, itsView=self.view)
        ruleSetItem.addRule(ruleItem)
        return ruleSetItem

    def testExportRecurrence(self):
        eastern = self.view.tzinfo.getInstance("America/New_York")
        start = datetime.datetime(2005,2,1, tzinfo = eastern)
        vevent = vobject.icalendar.RecurringComponent(name='VEVENT')
        vevent.behavior = vobject.icalendar.VEvent

        vevent.add('dtstart').value = start

        ruleSetItem = self._makeRecurrenceRuleSet()
        vevent.rruleset = ruleSetItem.createDateUtilFromRule(start)
        
        self.assertEqual(vevent.rrule.value, 'FREQ=DAILY')

        event = Calendar.CalendarEvent(itsView = self.view)
        event.anyTime = False
        event.summary = uw("blah")
        event.startTime = start
        event.endTime = datetime.datetime(2005,2,1,1, tzinfo = eastern)

        event.rruleset = self._makeRecurrenceRuleSet(
            datetime.datetime(2005,3,1, tzinfo = eastern),
            freq='weekly',
            byweekday=[WeekdayAndPositionStruct(i, 0) for i in "tuesday", "thursday"]
        )
        
        vcalendar = getVObjectData(self.view, [event.itsItem])

        self.assertEqual(vcalendar.vevent.dtstart.serialize(),
                         'DTSTART;TZID=America/New_York:20050201T000000\r\n')
        vcalendar.vevent = vcalendar.vevent.transformFromNative()
        self.assertEqual(vcalendar.vevent.rrule.serialize(),
                         'RRULE:FREQ=WEEKLY;BYDAY=TU,TH;UNTIL=20050302T045900Z\r\n')

        # move the second occurrence one day later
        nextEvent = event.getFirstOccurrence().getNextOccurrence()
        nextEvent.changeThis(pim.EventStamp.startTime.name,
                             datetime.datetime(2005,2,9,
                                               tzinfo=self.view.tzinfo.floating))

        nextEvent.getNextOccurrence().deleteThis()

        vcalendar = getVObjectData(self.view, [event.itsItem, nextEvent])
        for ev in vcalendar.vevent_list:
            if hasattr(ev, 'recurrence_id'):
                modified = ev
            else:
                master = ev
        self.assertEqual(modified.dtstart.serialize(),
                         'DTSTART:20050209T000000\r\n')
        self.assertEqual(modified.recurrence_id.serialize(),
                         'RECURRENCE-ID;TZID=America/New_York:20050203T000000\r\n')
        self.assertEqual(master.exdate.serialize(),
                         'EXDATE;TZID=America/New_York:20050210T000000\r\n')
        vcalendar.behavior.generateImplicitParameters(vcalendar)
        self.assertEqual(vcalendar.vtimezone.tzid.value, "America/New_York")

    def _testImportOracleModification(self):    # XXX this test is broken
        # switch to no-timezones mode
        schema.ns('osaf.pim', self.view).TimezonePrefs.showUI = False
        # Oracle modifies recurring events by first, if the time changed, adding
        # an EXDATE for the old time plus an RDATE for the new time, then
        # creating a VEVENT with RECURRENCE-ID matching the RDATE, except the
        # RECURRENCE-ID is in UTC, as is the modifications DTSTART.
        self.Import(self.view, u'oracle_mod.ics')
        master = pim.EventStamp(sharing.findUID(self.view,
                                        'abbfc510-4d8f-11db-c525-001346a711f0'))
        modTime = datetime.datetime(2006, 9, 29, 13, tzinfo=self.utc)
        changed = master.getRecurrenceID(modTime)
        self.assert_(changed is not None)
        self.assertEqual(changed.itsItem.displayName,
                         "Modification title changed")
        
        # test that a few of the custom fields were preserved when exporting
        
        vcalendar = getVObjectData(self.view, [master.itsItem])
        self.assertEqual(vcalendar.vevent.organizer.params['X-ORACLE-GUID'][0],
                         '07FC24E37F395815E0405794071A700C')
        self.assertEqual(vcalendar.vevent.created.value, '20060926T202203Z')
        
    def testMismatchedStartEndTimezones(self):
        self.Import(self.view, u'start_end_timezones.ics')
        
        event = pim.EventStamp(sharing.findUID(self.view,
                                       'c1ea7e4c-c13f-11db-a49c-a07b7a7d67f5'))
        self.failUnlessEqual(event.startTime.tzinfo, self.view.tzinfo.floating)


    def testDisplayAlarm(self):
        """Check we initialize a Reminder correctly from a VALARM element"""
        self.Import(self.view, 'DisplayAlarm.ics')
        
        eventItem = sharing.findUID(self.view, 'eventfrombug10958')
                                    
        reminder = eventItem.getUserReminder()
        self.failUnless(reminder is not None, "Reminder not set up from VALARM")
        self.failUnlessEqual(reminder.duration, datetime.timedelta(days=1))
        self.failUnlessEqual(reminder.repeat, 4)
        self.failUnlessEqual(reminder.description, u'Wake up!')
        self.failUnlessEqual(reminder.delta, datetime.timedelta(days=-5))


# test import/export unicode

class TimeZoneTestCase(SharedSandboxTestCase):

    def getICalTzinfo(self, lines):
        fileobj = cStringIO.StringIO("\r\n".join(lines))
        parsed = tz.tzical(fileobj)

        return parsed.get()

    def runConversionTest(self, expectedZone, icalZone):
        dt = datetime.datetime(2004, 10, 11, 13, 22, 21, tzinfo=icalZone)
        convertedZone = convertToICUtzinfo(self.view, dt).tzinfo
        self.failUnless(isinstance(convertedZone, (ICUtzinfo, FloatingTZ)))
        self.failUnlessEqual(expectedZone, convertedZone)

        dt = datetime.datetime(2004, 4, 11, 13, 9, 56, tzinfo=icalZone)
        convertedZone = convertToICUtzinfo(self.view, dt).tzinfo
        self.failUnless(isinstance(convertedZone, (ICUtzinfo, FloatingTZ)))
        self.failUnlessEqual(expectedZone, convertedZone)

    def testVenezuela(self):
        zone = self.getICalTzinfo([
            "BEGIN:VTIMEZONE",
            "TZID:America/Caracas",
            "LAST-MODIFIED:20050817T235129Z",
            "BEGIN:STANDARD",
            "DTSTART:19321213T204552",
            "TZOFFSETTO:-0430",
            "TZOFFSETFROM:+0000",
            "TZNAME:VET",
            "END:STANDARD",
            "BEGIN:STANDARD",
            "DTSTART:19650101T000000",
            "TZOFFSETTO:-0400",
            "TZOFFSETFROM:-0430",
            "TZNAME:VET",
            "END:STANDARD",
            "END:VTIMEZONE"])

        self.runConversionTest(
            self.view.tzinfo.getInstance("America/Caracas"),
            zone)

    def testAustralia(self):

        zone = self.getICalTzinfo([
            "BEGIN:VTIMEZONE",
            "TZID:Australia/Sydney",
            "LAST-MODIFIED:20050817T235129Z",
            "BEGIN:STANDARD",
            "DTSTART:20050326T160000",
            "TZOFFSETTO:+1000",
            "TZOFFSETFROM:+0000",
            "TZNAME:EST",
            "END:STANDARD",
            "BEGIN:DAYLIGHT",
            "DTSTART:20051030T020000",
            "TZOFFSETTO:+1100",
            "TZOFFSETFROM:+1000",
            "TZNAME:EST",
            "END:DAYLIGHT",
            "END:VTIMEZONE"])

        self.runConversionTest(
            self.view.tzinfo.getInstance("Australia/Sydney"),
            zone)

    def testFrance(self):

        zone = self.getICalTzinfo([
            "BEGIN:VTIMEZONE",
            "TZID:Europe/Paris",
            "LAST-MODIFIED:20050817T235129Z",
            "BEGIN:DAYLIGHT",
            "DTSTART:20050327T010000",
            "TZOFFSETTO:+0200",
            "TZOFFSETFROM:+0000",
            "TZNAME:CEST",
            "END:DAYLIGHT",
            "BEGIN:STANDARD",
            "DTSTART:20051030T030000",
            "TZOFFSETTO:+0100",
            "TZOFFSETFROM:+0200",
            "TZNAME:CET",
            "END:STANDARD",
            "END:VTIMEZONE"])

        self.runConversionTest(
            self.view.tzinfo.getInstance("Europe/Paris"),
            zone)

    def testUS(self):
        zone = self.getICalTzinfo([
            "BEGIN:VTIMEZONE",
            "TZID:America/Los_Angeles",
            "LAST-MODIFIED:20050817T235129Z",
            "BEGIN:DAYLIGHT",
            "DTSTART:20050403T100000",
            "TZOFFSETTO:-0700",
            "TZOFFSETFROM:+0000",
            "TZNAME:PDT",
            "END:DAYLIGHT",
            "BEGIN:STANDARD",
            "DTSTART:20051030T020000",
            "TZOFFSETTO:-0800",
            "TZOFFSETFROM:-0700",
            "TZNAME:PST",
            "END:STANDARD",
            "END:VTIMEZONE"])
        self.runConversionTest(
            self.view.tzinfo.getInstance("America/Los_Angeles"),
            zone)

    def testExchangeUSEastern(self):
        zone = self.getICalTzinfo([
            "BEGIN:VTIMEZONE",
            "TZID:GMT -0500 (Standard) / GMT -0400 (Daylight)",
            "BEGIN:STANDARD",
            "DTSTART:16010101T020000",
            "TZOFFSETFROM:-0400",
            "TZOFFSETTO:-0500",
            "RRULE:FREQ=YEARLY;WKST=MO;INTERVAL=1;BYMONTH=11;BYDAY=1SU",
            "END:STANDARD",
            "BEGIN:DAYLIGHT",
            "DTSTART:16010101T020000",
            "TZOFFSETFROM:-0500",
            "TZOFFSETTO:-0400",
            "RRULE:FREQ=YEARLY;WKST=MO;INTERVAL=1;BYMONTH=3;BYDAY=2SU",
            "END:DAYLIGHT",
            "END:VTIMEZONE"])
        # What timezone is chosen unfortunately depends on the order of
        # timezones in PyICU.  America/Detroit comes before America/New_York
        # and their TZ transitions are equivalent in the 21st century.
        # If a view was passed to convertToICUtzinfo, this would be
        # America/New_York because it's a well known TZID.
        self.runConversionTest(
            self.view.tzinfo.getInstance("America/New_York"),
            zone)

class SharingTestCase(SharedSandboxTestCase):
    def setUp(self):
        super(SharingTestCase, self).setUp()
        self.peer = pim.EmailAddress.getEmailAddress(self.view, 
                                                     "conflict@example.com")
        self.utc = self.view.tzinfo.getInstance('utc')
    
class ImportTodoTestCase(SharingTestCase):
    
    def runImport(self, *lines):
        text = "\r\n".join(lines)
        items = deserialize(self.view, self.peer, text, 
                            translator.SharingTranslator, ics.ICSSerializer)
        self.items = items
        return items
    
    def testSimple(self):
        self.runImport(
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            "BEGIN:VTODO",
            "DTSTART:20060213T000000",
            "SUMMARY:A ToDo",
            "UID:4A7707B5-6E87-49ED-8871-7A0BD37F0349",
            "SEQUENCE:2",
            "DTSTAMP:20060227T163229Z",
            "END:VTODO",
            "END:VCALENDAR"
        )
        
        self.failUnlessEqual(1, len(self.items))
        
        item = self.items[0]
        
        self.failIf(pim.has_stamp(item, pim.TaskStamp))
        self.failUnless(pim.has_stamp(item, pim.EventStamp))
        self.failUnlessEqual(item.displayName, u"A ToDo")
        self.failUnlessEqual(item.triageStatus, pim.TriageEnum.now)
        self.failIf(item.needsReply)

    def testStarred(self):
        self.runImport(
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            "BEGIN:VTODO",
            "X-OSAF-STARRED:TRUE",
            "DTSTART:20060213T000000",
            "SUMMARY:A Starred Note",
            "UID:4A7707B5-6E87-49ED-8871-7A0BD37F0355",
            "SEQUENCE:26",
            "DTSTAMP:20080227T163229Z",
            "END:VTODO",
            "END:VCALENDAR"
        )
        item = self.items[0]
        task = pim.TaskStamp(item)
        
        self.failUnless(pim.has_stamp(task, pim.TaskStamp))
        self.failUnless(pim.has_stamp(task, pim.EventStamp))
        self.failUnlessEqual(item.displayName, u"A Starred Note")
        self.failUnlessEqual(task.itsItem.triageStatus, pim.TriageEnum.now)
        self.failIf(task.itsItem.needsReply)

    def testDueDate(self):
        self.runImport(
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            "BEGIN:VTODO",
            "DTSTART:20060213T000000",
            "SUMMARY:Deferred ToDo",
            "STATUS:CANCELLED",
            "UID:B75093D9-432F-4684-8DB7-744AAB7F747B",
            "SEQUENCE:4",
            "DTSTAMP:20060227T203912Z",
            "DUE;VALUE=DATE:20070121",
            "END:VTODO",
            "END:VCALENDAR"
        )
        
        self.failUnlessEqual(1, len(self.items))
        
        item = self.items[0]
        
        self.failIf(pim.has_stamp(item, pim.TaskStamp))
        self.failUnless(pim.has_stamp(item, pim.EventStamp))
        self.failUnlessEqual(item.displayName, u"Deferred ToDo")
        self.failUnlessEqual(pim.EventStamp(item).startTime.date(),
                             datetime.date(2007, 1, 21))
        self.failUnlessEqual(item.triageStatus, pim.TriageEnum.later)

    def testStatus(self):
        self.runImport(
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            "BEGIN:VTODO",
            "DTSTART:20060213T000000",
            "SUMMARY:ToDone",
            "DTSTAMP:20060227T203912Z",
            "UID:DD5D311A-F73F-4611-B463-A5766A1BAE5F",
            "SEQUENCE:6",
            "STATUS:COMPLETED",
            "END:VTODO",
            "END:VCALENDAR"
        )
        
        self.failUnlessEqual(1, len(self.items))
        
        item = self.items[0]
        task = pim.TaskStamp(item)
        
        self.failUnless(pim.has_stamp(task, pim.TaskStamp))
        self.failUnlessEqual(task.summary, u"ToDone")
        self.failUnlessEqual(task.itsItem.triageStatus, pim.TriageEnum.done)

    def testStatus(self):
        self.runImport(
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            "BEGIN:VTODO",
            "DTSTART:20060213T000000",
            "SUMMARY:ToDone",
            "DTSTAMP:20060227T203912Z",
            "UID:DD5D311A-F73F-4611-B463-A5766A1BAE5F",
            "SEQUENCE:6",
            "STATUS:COMPLETED",
            "END:VTODO",
            "END:VCALENDAR"
        )
        
        self.failUnlessEqual(1, len(self.items))
        
        item = self.items[0]
        
        self.failIf(pim.has_stamp(item, pim.TaskStamp))
        self.failUnlessEqual(item.displayName, u"ToDone")
        self.failUnlessEqual(item.triageStatus, pim.TriageEnum.done)

    def testNeedsAction(self):
        self.runImport(
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            "BEGIN:VTODO",
            "X-OSAF-STARRED:TRUE",
            "DTSTART:20060213T000000",
            "SUMMARY:Really\, do this right away",
            "DTSTAMP:20060227T203912Z",
            "UID:1E192668-99F7-4FA1-B1F7-70A05FC8E357",
            "SEQUENCE:6",
            "STATUS:NEEDS-ACTION",
            "END:VTODO",
            "END:VCALENDAR"
        )
        
        self.failUnlessEqual(1, len(self.items))
        
        item = self.items[0]
        task = pim.TaskStamp(item)
        
        self.failUnless(pim.has_stamp(task, pim.TaskStamp))
        self.failUnlessEqual(task.summary, u"Really, do this right away")
        self.failUnlessEqual(task.itsItem.triageStatus, pim.TriageEnum.now)
        self.failUnless(task.itsItem.needsReply)

    def testInProcess(self):
        self.runImport(
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            "BEGIN:VTODO",
            "DTSTART:20060213T000000",
            "SUMMARY:I'm busy!",
            "DTSTAMP:20060227T203912Z",
            "UID:48F6177A-3EEF-423B-ABBA-0B506189FD29",
            "SEQUENCE:1",
            "STATUS:IN-PROCESS",
            "END:VTODO",
            "END:VCALENDAR"
        )
        
        self.failUnlessEqual(1, len(self.items))
        
        item = self.items[0]
        
        self.failIf(pim.has_stamp(item, pim.TaskStamp))
        self.failUnlessEqual(item.displayName, u"I'm busy!")
        self.failUnlessEqual(item.triageStatus, pim.TriageEnum.now)
        self.failIf(item.needsReply)

    def testCompleted(self):
        self.runImport(
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            "BEGIN:VTODO",
            "DTSTART:20060213T000000",
            "SUMMARY:ToDoneAndWhen",
            "DTSTAMP:20060227T203912Z",
            "UID:DD5D311A-F73F-4619-B463-A5766A1BAE5F",
            "SEQUENCE:6",
            "STATUS:COMPLETED",
            "COMPLETED:20060301T010000Z",
            "END:VTODO",
            "END:VCALENDAR"
        )
        
        self.failUnlessEqual(1, len(self.items))
        
        item = self.items[0]
        task = pim.TaskStamp(item)
        
        self.failIf(pim.has_stamp(task, pim.TaskStamp))
        self.failUnlessEqual(task.summary, u"ToDoneAndWhen")
        self.failUnlessEqual(task.itsItem.triageStatus, pim.TriageEnum.done)
        expectedTSC = datetime.datetime(2006, 3, 1, 1, 0, 0, 0, self.utc)
        self.failUnlessEqual(task.itsItem.triageStatusChanged,
                             Triageable.makeTriageStatusChangedTime(self.view, expectedTSC))

    def testDescription(self):
        self.runImport(
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            "BEGIN:VTODO",
            "UID:2C41172C-6812-4848-A9BA-73A827B06E28",
            "SEQUENCE:7",
            "STATUS:COMPLETED",
            "SUMMARY:To Do",
            "X-OSAF-STARRED:true",
            "COMPLETED:20060227T080000Z",
            "DESCRIPTION:This is a very important TODO:\\n\\n\xe2\x80\xa2 Do one thing\\n\xe2\x80\xa2 Do somet",
            " hing else",
            "END:VTODO",
            "END:VCALENDAR"
        )
        
        self.failUnlessEqual(1, len(self.items))
        
        item = self.items[0]
        task = pim.TaskStamp(item)
        
        self.failUnless(pim.has_stamp(task, pim.TaskStamp))
        self.failUnlessEqual(item.body,
                u"This is a very important TODO:\n\n\u2022 Do one thing\n\u2022 Do something else")
        self.failUnlessEqual(item.triageStatus, pim.TriageEnum.done)


    def testUpdate(self):
        self.runImport(
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            "BEGIN:VTODO",
            "DTSTART:20060214T000000",
            "SUMMARY:To Do (Initial)",
            "UID:ED5CAC89-4BEE-4903-8DE8-1AEF6FC1D431",
            "DTSTAMP:20060227T233332Z",
            "SEQUENCE:11",
            "DESCRIPTION:How will I ever get this done?",
            "END:VTODO",
            "END:VCALENDAR",
        )
        self.runImport(
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            "BEGIN:VTODO",
            "DTSTART:20060214T000000",
            "SUMMARY:To Do (Initial)",
            "X-OSAF-STARRED:TRUE",
            "UID:ED5CAC89-4BEE-4903-8DE8-1AEF6FC1D431",
            "DTSTAMP:20060227T233332Z",
            "SEQUENCE:12",
            "DESCRIPTION:Phew!",
            "STATUS:COMPLETED",
            "DUE;VALUE=DATE:20060327",
            "END:VTODO",
            "END:VCALENDAR",
        )
        
        self.failUnlessEqual(1, len(self.items))
        
        item = self.items[0]
        task = pim.TaskStamp(item)
        
        self.failUnless(pim.has_stamp(task, pim.TaskStamp))
        self.failUnless(pim.has_stamp(task, pim.EventStamp))
        self.failUnlessEqual(item.body, u"Phew!")
        self.failUnlessEqual(pim.EventStamp(task).startTime.date(),
                             datetime.date(2006, 3, 27))
        # the update causes a (spurious, but such is life) conflict
        self.failUnlessEqual(task.itsItem.triageStatus, pim.TriageEnum.now)
        # resolve the conflicts
        for c in sharing.getConflicts(task.itsItem):
            c.apply()
        self.failUnlessEqual(task.itsItem.triageStatus, pim.TriageEnum.done)


class ExportTodoTestCase(SharingTestCase):
    def getExportedTodoComponent(self, **todoParams):
        """
        Utility method to reparse the iCalendar content
        we've generated, so that we can check that it's
        what we expect.
        """
        create = todoParams.pop('create', pim.Task)
        new = create(itsView=self.view)
        new.InitOutgoingAttributes() # simulate creation in the Chandler UI
        
        item = getattr(new, 'itsItem', new)
        for attr, value in todoParams.iteritems():
            setattr(item, attr, value)
        
        iCalendarContent = serialize(self.view, [item],
                                     translator.SharingTranslator,
                                     ics.ICSSerializer)

        self.failUnlessEqual(type(iCalendarContent), str)
        # Could in general add a check for utf-8 decodability

        io = cStringIO.StringIO(iCalendarContent)

        components = list(vobject.readComponents(io, validate=True))
        self.failUnlessEqual(len(components), 1,
                            "exportProcess should create a single calendar")
        
        calendar = components[0]

        # We expect exactly one child component ...
        self.failUnlessEqual(len(list(calendar.components())), 1)
        
        vobj = list(calendar.components())[0]
        self.failUnlessEqual(item.itsUUID.str16(),
                             vobj.getChildValue('uid'))
        
        return (item, vobj)



    def testSimple(self):
        item, vobj = self.getExportedTodoComponent(displayName=u'Important')
        
        self.failUnlessEqual(vobj.name.lower(), 'vtodo')
        self.failUnless(pim.has_stamp(item, pim.TaskStamp))
        self.failUnlessEqual(vobj.getChildValue('x_osaf_starred').lower(),
                            'true')
        self.failUnlessEqual(u'Important', vobj.getChildValue('summary'))
        

    def testDueDate(self):
        task, vtodo = self.getExportedTodoComponent(
                        displayName=u'Some stupid task')

        self.failUnlessEqual(u'Some stupid task',
                             vtodo.getChildValue('summary'))
        
    def testStatus(self):
        task, vobj = self.getExportedTodoComponent(
                create=pim.Note,
                displayName=u'Some completed stupid task',
                _triageStatus=pim.TriageEnum.done,
                needsReply=True)

        self.failUnlessEqual(vobj.name.lower(), 'vtodo')
        self.failUnlessEqual(vobj.getChildValue('x_osaf_starred', self), self)        
        self.failUnlessEqual(u'Some completed stupid task',
                             vobj.getChildValue('summary'))
        
        self.failUnlessEqual(vobj.getChildValue('status').lower(), 'completed')

    def testLaterStatus(self):
        task, vobj = self.getExportedTodoComponent(
                create=pim.Note,
                displayName=u'Some deferred task',
                _triageStatus=pim.TriageEnum.later)
        self.failUnlessEqual(u'Some deferred task',
                             vobj.getChildValue('summary'))

        self.failUnlessEqual(vobj.name.lower(), 'vtodo')
        self.failUnlessEqual(vobj.getChildValue('x_osaf_starred', '').lower(),
                             '')
        self.failUnlessEqual(vobj.getChildValue('status').lower(),
                             u'cancelled')

    def testTaskEvent(self):
        item, vobj = self.getExportedTodoComponent(
                **{'create': pim.Note,
                   'displayName': u'Some deferred task',
                   '_triageStatus': pim.TriageEnum.later,
                   pim.Stamp.stamp_types.name: set([pim.EventStamp, pim.TaskStamp]),
                })
                        
        self.failUnlessEqual(vobj.name.lower(), 'vevent')
        self.failUnlessEqual(vobj.getChildValue('x_osaf_starred').lower(),
                             'true')
        self.failUnlessEqual(u'Some deferred task',
                             vobj.getChildValue('summary'))
        
    def testNeedsReplyStatus(self):
        item, vobj = self.getExportedTodoComponent(
                displayName=u'Very important, Bob',
                _triageStatus=pim.TriageEnum.now,
                needsReply=True)
                
        self.failUnlessEqual(vobj.name.lower(), 'vtodo')
        self.failUnlessEqual(vobj.getChildValue('x_osaf_starred').lower(),
                             'true')
        self.failUnlessEqual(u'Very important, Bob',
                             vobj.getChildValue('summary'))
        self.failUnlessEqual(u'needs-action',
                             vobj.getChildValue('status').lower())
        
    def testDescription(self):
        body = u"This is a great \u201cdescription\u201d\n"
        
        item, vobj = self.getExportedTodoComponent(
            create=pim.Note,
            displayName=u'Who cares',
            body=body)
            
        self.failUnlessEqual(vobj.name.lower(), 'vtodo')
        self.failUnlessEqual(vobj.getChildValue('x_osaf_starred', '').lower(),
                             '')
        self.failUnlessEqual(vobj.getChildValue('description'), body)


class ICalUIDTestCase(NRVTestCase):
        
    def testWrapper(self):
        task = pim.Task(itsView=self.view, displayName=u"task test")
        
        taskItem = task.itsItem
        
        # Check that we get back the correct initialValue.
        self.failUnlessEqual(taskItem.icalUID, str(taskItem.itsUUID))
        
        taskItem.icalUID = u'999-9999'
        getattrUID = getattr(taskItem, Note.icalUID.name)
        
        self.failUnlessEqual(u'999-9999', getattrUID)
        
    def testCreate(self):
        eventCreateDict = {
            'itsView': self.view,
            'summary': u'event creation test',
            Note.icalUID.name: u'abcdef',
            'startTime': datetime.datetime(1996, 11, 11)
        }
        event = Calendar.CalendarEvent(**eventCreateDict)
        
        self.failUnlessEqual(u'abcdef', event.itsItem.icalUID)
        

    def testFindEventUID(self):
        uid = u'123'
        
        self.failUnless(sharing.findUID(self.view, uid) is None)

        
        event = Calendar.CalendarEvent(
            itsView = self.view,
            displayName = u"event test",
            startTime = datetime.datetime(2010, 1, 1, 10),
            duration = datetime.timedelta(hours=2))

        self.failUnless(sharing.findUID(self.view, uid) is None)
        
        item = event.itsItem
        setattr(item, Note.icalUID.name, uid)
            
        self.failUnless(sharing.findUID(self.view, uid) is item)
        
    def testDelete(self):
        task = pim.Task(itsView=self.view)
        
        # Set the task's UID ....
        task.itsItem.icalUID = u'yay'
        
        # Delete it ...
        task.itsItem.delete(recursive=True)
        
        # ... and fail if it can still be found
        self.failIf(sharing.findUID(self.view, u'yay') is not None)

    def testUpdate(self):
        uid = u'on-a-limo-to-milano-solo-gigolos-dont-nod'
        
        task = pim.Task(itsView=self.view)
        task.itsItem.icalUID = uid
        
        event = Calendar.CalendarEvent(itsView=self.view,
                               startTime=datetime.datetime(2000, 1, 1))
                               
        event.itsItem.icalUID = uid
        del task.itsItem.icalUID # Necessary?
        
        self.failUnless(event.itsItem is sharing.findUID(self.view, uid))


""" # TODO: Replace this with something that doesn't use old style format

class ICalendarMergeTestCase(SharedSandboxTestCase):
    ETAG = 0
    before = None
    after = None

    def setUp(self):
        super(ICalendarMergeTestCase, self).setUp()
        
        view = self.view

        collection = ListCollection("testCollection", self.sandbox,
                                    displayName=uw("Test Collection"))

        share = sharing.Share(itsView=view, contents=collection,
            conduit=sharing.InMemoryConduit(itsView=view,
                                            shareName=uw("viewmerging")),
            format=sharing.CalDAVFormat(itsView=view)
        )

        view.commit()
        
        self.shareUUID = share.itsUUID
        
    @property
    def collection(self):
        return self.share.contents
        
    @property
    def share(self):
        return self.view.findUUID(self.shareUUID)

    def _doSync(self, *icalendarLines):

        if not self.share.exists():
            self.share.create()

        # directly inject the data on the "server" ... i.e. the Conduit
        data = "\r\n".join(icalendarLines)
        self.share.conduit.inject('import.ics', data)

        # Now sync; it's as if icalendarLines were what was on the server
        self.share.sync()
        
        
    def testUpdateMod(self):
        # Test for one problem in bug 7019
        # Create the original ... (We could also use self._doSync here)
        startTime = datetime.datetime(2006, 4, 17, 13,
                                      tzinfo=self.view.tzinfo.floating)
        
        rrule = RecurrenceRule(
            itsParent=self.sandbox,
            freq="weekly"
        )
        rruleset = RecurrenceRuleSet(
            itsParent=self.sandbox,
            rrules=[rrule]
        )
        event = pim.CalendarEvent(
            itsParent=self.sandbox,
            startTime=startTime,
            duration=datetime.timedelta(hours=1),
            summary=u'Meeting Weakly',
            allDay=False,
            anyTime=False,
            icalUID=u'9cf1f128-c416-11da-9051-000a95d7eed8',
        )
        
        event.rruleset = rruleset
        self.collection.add(event.itsItem)
        
        # Change the occurrence on September 4 to 4pm on the 6th
        recurrenceID = startTime.replace(month=9, day=4)
        newStartTime = recurrenceID.replace(day=6, hour=16)
        occurrence = event.getRecurrenceID(recurrenceID)
        occurrence.changeThis(pim.EventStamp.startTime.name, newStartTime)
        
        self.view.commit()
        
        # Now import the iCalendar
        self._doSync(
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "BEGIN:VEVENT",
            "UID:9cf1f128-c416-11da-9051-000a95d7eed8",
            "DTSTART:20060828T130000",
            "DTEND:20060828T140000",
            "DESCRIPTION:\n",
            "RRULE:FREQ=WEEKLY;COUNT=20",
            "SUMMARY:PPD meeting",
            "END:VEVENT",
            "BEGIN:VEVENT",
            "UID:9cf1f128-c416-11da-9051-000a95d7eed8",
            "RECURRENCE-ID:20060904T130000",
            "DTSTART:20060906T160000",
            "DTEND:20060906T170000",
            "DESCRIPTION:\n",
            "SUMMARY:Meeting Weakly",
            "END:VEVENT",
            "BEGIN:VEVENT",
            "UID:9cf1f128-c416-11da-9051-000a95d7eed8",
            "RECURRENCE-ID:20061016T130000",
            "DTSTART:20061016T141500",
            "DTEND:20061016T151500",
            "DESCRIPTION:\n",
            "SUMMARY:Meeting Weakly",
            "END:VEVENT",
            "END:VCALENDAR"
        )

        sharedItem = self.collection.first()
        self.failUnless(pim.has_stamp(sharedItem, pim.EventStamp))
        
        sharedEvent = pim.EventStamp(sharedItem)
        self.failUnlessEqual(sharedEvent.startTime.replace(tzinfo=None),
                             datetime.datetime(2006, 8, 28, 13))
                             
        mods = [evt for evt in sharedEvent.modifications if
                not pim.EventStamp(evt).isTriageOnlyModification()]
        self.failUnlessEqual(len(mods), 2, "Wrong number of modifications after import")

        eventMod = pim.EventStamp(mods[1])


        self.failUnlessEqual(eventMod.startTime.replace(tzinfo=None),
                             datetime.datetime(2006, 10, 16, 14, 15))
        self.failUnlessEqual(eventMod.recurrenceID.replace(tzinfo=None),
                             datetime.datetime(2006, 10, 16, 13))

    def testExcludeOccurrence(self):
        Calendar.ensureIndexed(self.collection)
    
        self._doSync(
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "BEGIN:VEVENT",
            "UID:f60de354-5ef1-11db-ea01-f67872a529d1",
            "DTSTART:20061015T103000",
            "DTEND:20061015T113000",
            "DESCRIPTION:",
            "RRULE:FREQ=DAILY;UNTIL=20061112T235900",
            "SUMMARY:Daily",
            "END:VEVENT",
            "END:VCALENDAR"
       )

        self._doSync(
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "BEGIN:VEVENT",
            "UID:f60de354-5ef1-11db-ea01-f67872a529d1",
            "DTSTART:20061015T103000",
            "DTEND:20061015T113000",
            "EXDATE:20061016T103000",
            "DESCRIPTION:",
            "RRULE:FREQ=DAILY;UNTIL=20061112T235900",
            "SUMMARY:Daily",
            "END:VEVENT",
            "END:VCALENDAR"
        )
        
        start = datetime.datetime(2006, 10, 14, 
                                  tzinfo=self.view.tzinfo.floating)
        end = start + datetime.timedelta(days=7)
        events = list(Calendar.recurringEventsInRange(self.view, start, end,
                                                 filterColl=self.collection))
                                                  
        self.failUnlessEqual(len(events), 5)
"""

if __name__ == "__main__":
    unittest.main()
