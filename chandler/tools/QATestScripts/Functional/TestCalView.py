import tools.QAUITestAppLib as QAUITestAppLib
    
# initialization
fileName = "TestCalView.log"
logger = QAUITestAppLib.QALogger(fileName, "TestCalView")

try:
    # creation
    testView = QAUITestAppLib.UITestView(logger)
    # action
    # switch to calendar view
    testView.SwitchToCalView()
    # double click in the calendar view => event creation or selection
    ev = testView.DoubleClickInCalView()
    # double click one more time => edit the title
    testView.DoubleClickInCalView()
    # type a new title and return
    QAUITestAppLib.scripting.User.emulate_typing("foo")
    QAUITestAppLib.scripting.User.emulate_return()
    
    # verification
    # check the detail view of the created event
    ev.Check_DetailView({"displayName":"foo"})

finally:
    # cleaning
    logger.Close()
