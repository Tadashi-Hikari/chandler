
__revision__  = "$Revision$"
__date__      = "$Date$"
__copyright__ = "Copyright (c) 2002 Open Source Applications Foundation"
__license__   = "http://osafoundation.org/Chandler_0.1_license_terms.htm"


import repository.item.Item

from repository.util.UUID import UUID

class ReadOnlyError(ValueError):
    "thrown when a read-only collection is modified"
    

class PersistentCollection(object):
    '''A persistence aware collection, tracking changes into a dirty bit.

    This class is abstract and is to be used together with a concrete
    collection class such as list or dict.'''

    def __init__(self, item, companion):

        super(PersistentCollection, self).__init__()

        self._dirty = False
        self._readOnly = False
        self.__setItem(item, companion)

    def setReadOnly(self, readOnly=True):

        self._readOnly = readOnly

    def isReadOnly(self):

        return self._readOnly

    def _setItem(self, item, companion):

        if self._item is not None and self._item is not item:
            raise ValueError, "Collection already owned by %s" %(self._item)

        self.__setItem(item, companion)
        for value in self.itervalues():
            if isinstance(value, PersistentCollection):
                value._setItem(item, companion)

    def __setItem(self, item, companion):
        
        self._item = item
        self._companion = companion

    def _setDirty(self):

        if self._readOnly:
            raise ReadOnlyError, 'collection is read-only'

        if not self._dirty and self._item:
            self._dirty = True
            self._item.setDirty()

    def _prepareValue(self, value):

        if isinstance(value, list):
            value = PersistentList(self._item, self._companion, *value)
        elif isinstance(value, dict):
            value = PersistentDict(self._item, self._companion, **value)
        elif isinstance(value, repository.item.Item.Item):
            value = SingleRef(value.getUUID())

        return value

    def _restoreValue(self, value):

        if isinstance(value, SingleRef):
            uuid = value.getUUID()
            if self._companion is None:
                return self._item.find(uuid)
            else:
                return self._item.getAttributeValue(self._companion).get(uuid)

        return value

    def _storeValue(self, value):

        if self._companion is not None:
            if isinstance(value, repository.item.Item.Item):
                if not self._item.hasValue(self._companion, value):
                    self._item.addValue(self._companion, value)


class PersistentList(list, PersistentCollection):
    'A persistence aware list, tracking changes into a dirty bit.'

    def __init__(self, item, companion, *args):

        list.__init__(self)
        PersistentCollection.__init__(self, item, companion)

        if args:
            self.extend(args)

    def __setitem__(self, index, value):

        self._storeValue(value)
        value = self._prepareValue(value)
        self._setDirty()
        super(PersistentList, self).__setitem__(index, value)

    def __delitem__(self, index):

        self._setDirty()
        super(PersistentList, self).__delitem__(index)        

    def __setslice__(self, start, end, value):

        for v in value:
            self._storeValue(v)
        value = [self._prepareValue(v) for v in value]
        self._setDirty()
        super(PersistentList, self).__setslice__(start, end, value)

    def __delslice__(self, start, end):

        self._setDirty()
        super(PersistentList, self).__delslice__(start, end)

    def __iadd__(self, value):

        for v in value:
            self._storeValue(v)
        value = [self._prepareValue(v) for v in value]
        self._setDirty()
        super(PersistentList, self).__iadd__(value)

    def __imul__(self, value):

        self._setDirty()
        super(PersistentList, self).__imul__(value)

    def append(self, value):

        self._storeValue(value)
        value = self._prepareValue(value)
        self._setDirty()
        super(PersistentList, self).append(value)

    def insert(self, index, value):

        self._storeValue(value)
        value = self._prepareValue(value)
        self._setDirty()
        super(PersistentList, self).insert(index, value)

    def pop(self, index = -1):

        self._setDirty()
        return super(PersistentList, self).pop(index)

    def remove(self, value):

        value = self._prepareValue(value)
        self._setDirty()
        super(PersistentList, self).remove(value)

    def reverse(self):

        self._setDirty()
        super(PersistentList, self).reverse()

    def sort(self, *args):

        self._setDirty()
        super(PersistentList, self).sort(*args)

    def extend(self, value):

        for v in value:
            self._storeValue(v)
        value = [self._prepareValue(v) for v in value]
        self._setDirty()
        super(PersistentList, self).extend(value)

    def __getitem__(self, key):

        value = super(PersistentList, self).__getitem__(key)
        value = self._restoreValue(value)
        
        return value

    def __getslice__(self, start, end):

        value = super(PersistentList, self).__getslice__(start, end)
        value = [self._restoreValue(v) for v in value]

        return value

    def __iter__(self):

        for value in super(PersistentList, self).__iter__():
            yield self._restoreValue(value)

    def itervalues(self):

        return self.__iter__()

    def _itervalues(self):

        return super(PersistentList, self).__iter__()


class PersistentDict(dict, PersistentCollection):
    'A persistence aware dict, tracking changes into a dirty bit.'

    def __init__(self, item, companion, **kwds):

        dict.__init__(self)
        PersistentCollection.__init__(self, item, companion)

        if kwds:
            self.update(kwds)

    def __delitem__(self, key):

        self._setDirty()
        super(PersistentDict, self).__delitem__(key)

    def __setitem__(self, key, value):

        self._storeValue(value)
        value = self._prepareValue(value)
        self._setDirty()
        super(PersistentDict, self).__setitem__(key, value)

    def clear(self):

        self._setDirty()
        super(PersistentDict, self).clear()

    def update(self, value):

        self._storeValue(value)
        dictionary = {}
        for k, v in value.iteritems():
            dictionary[k] = self._prepareValue(v)
        self._setDirty()
        super(PersistentDict, self).update(dictionary)

    def setdefault(self, key, value=None):

        if not key in self:
            self._setDirty()

        self._storeValue(value)
        value = self._prepareValue(value)

        return super(PersistentDict, self).setdefault(key, value)

    def popitem(self):

        self._setDirty()

        value = super(PersistentDict, self).popitem()
        value = (value[0], self._restoreValue(value[1]))
        
        return value

    def __getitem__(self, key):

        value = super(PersistentDict, self).__getitem__(key)
        value = self._restoreValue(value)
        
        return value

    def itervalues(self):

        for value in super(PersistentDict, self).itervalues():
            yield self._restoreValue(value)

    def iteritems(self):

        for key, value in super(PersistentDict, self).iteritems():
            yield (key, self._restoreValue(value))

    def _itervalues(self):

        return super(PersistentDict, self).itervalues()

    def _iteritems(self):

        return super(PersistentDict, self).iteritems()


class SingleRef(object):

    __slots__ = "_uuid"

    def __init__(self, uuid):

        super(SingleRef, self).__init__()
        self._uuid = uuid

    def __str__(self):

        return self._uuid.str64()

    def __repr__(self):

        return "<ref: %s>" %(self._uuid.str16())

    def __getstate__(self):

        return self._uuid._uuid

    def __setstate__(self, state):

        self._uuid = UUID(state)
    
    def getUUID(self):

        return self._uuid

    def __cmp__(self, other):

        if not isinstance(other, SingleRef):
            raise TypeError, type(other)
        
        return self._uuid.__cmp__(other._uuid)
