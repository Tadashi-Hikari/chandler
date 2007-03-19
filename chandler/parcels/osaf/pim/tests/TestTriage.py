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

import unittest, os, datetime, time

import osaf.pim.tests.TestDomainModel as TestDomainModel
from osaf.pim import Note, TriageEnum, Triageable
from PyICU import ICUtzinfo

class TriageTest(TestDomainModel.DomainModelTestCase):
    def setUp(self):
        super(TriageTest, self).setUp()
        view = self.rep.view
        self.item = Note("triageTestItem", itsView=view)
        pass

    def testMakeTriageStatusChangedTime(self):
        # triageStatusChange is supposed to be a GMT time in seconds (negated
        # for sorting)... prove to myself that it's really GMT.
        now = datetime.datetime.now(ICUtzinfo.default)
        now_tsc = Triageable.makeTriageStatusChangedTime()
        ny_now = now.astimezone(ICUtzinfo.getInstance("America/New_York"))
        la_now = now.astimezone(ICUtzinfo.getInstance("America/Los_Angeles"))

        ny_tsc = Triageable.makeTriageStatusChangedTime(ny_now)
        la_tsc = Triageable.makeTriageStatusChangedTime(la_now)
        self.failUnlessEqual(ny_tsc, la_tsc)
        self.failUnless((la_tsc - now_tsc) < 1.0)

    def testInitialTriageState(self):        
        now = datetime.datetime.now(ICUtzinfo.default)
        self.failUnlessEqual(self.item.triageStatus, TriageEnum.now)
        self.failIf(hasattr(self.item, '_sectionTriageStatus'))
        self.failIf(hasattr(self.item, '_sectionTriageStatusChanged'))
        # tsc might not be exactly equal to the creation time, but it should
        # be close.
        self.failUnless(Triageable.makeTriageStatusChangedTime(self.item.createdOn) 
                        + self.item.triageStatusChanged < 1.0)

if __name__ == "__main__":
    unittest.main()