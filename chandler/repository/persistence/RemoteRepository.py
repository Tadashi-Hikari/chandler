
__revision__  = "$Revision$"
__date__      = "$Date$"
__copyright__ = "Copyright (c) 2002 Open Source Applications Foundation"
__license__   = "http://osafoundation.org/Chandler_0.1_license_terms.htm"


from repository.persistence.Repository import OnDemandRepository
from repository.persistence.Repository import RepositoryError
from repository.persistence.Repository import OnDemandRepositoryView
from repository.util.ClassLoader import ClassLoader


class RemoteRepository(OnDemandRepository):

    def __init__(self, transport):
        'Construct an RemoteRepository giving it a transport handler'
        
        super(RemoteRepository, self).__init__(None)
        self.store = transport
        
    def create(self, verbose=False):

        raise NotImplementedError, "RemoteRepository.create"

    def open(self, verbose=False, create=False):

        if not self.isOpen():
            super(RemoteRepository, self).open(verbose)
            module, className = self.store.open(create)
            self.viewClass = ClassLoader.loadClass(className, module)
            self._status |= self.OPEN

    def close(self, purge=False):

        if self.isOpen():
            self.store.close()
            self._status &= ~self.OPEN

    def call(self, method, *args):

        return self.store.call(method, *args)

    def _createView(self):

        return self.viewClass(self)

