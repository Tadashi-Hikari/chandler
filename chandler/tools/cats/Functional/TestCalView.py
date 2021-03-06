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

import tools.cats.framework.ChandlerTestLib as QAUITestAppLib
from tools.cats.framework.ChandlerTestCase import ChandlerTestCase
import osaf.framework.scripting as scripting
from i18n.tests import uw
import osaf.framework.scripting.User as User
    
class TestCalView(ChandlerTestCase):
    
    def startTest(self):
    
        # creation
        testView = QAUITestAppLib.UITestView(self.logger)
        # make user collection, since only user
        # collections can be displayed as a calendar
        col = QAUITestAppLib.UITestItem("Collection", self.logger)
        #name and then select collection
        col.SetDisplayName(uw("testCalView"))
        sb = QAUITestAppLib.App_ns.sidebar
        User.emulate_sidebarClick(sb, uw('testCalView'))
        
        # action
        # switch to calendar view
        testView.SwitchToCalView()       
        # double click in the calendar view => event creation or selection
        ev = testView.DoubleClickInCalView()         
        QAUITestAppLib.scripting.User.emulate_typing(uw("Writing tests"))
        QAUITestAppLib.scripting.User.emulate_return()
        
        # verification
        # check the detail view of the created event
        ev.Check_DetailView({"displayName":uw("Writing tests")})

