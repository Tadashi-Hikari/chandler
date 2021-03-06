/*
 *  Copyright (c) 2003-2007 Open Source Applications Foundation
 *
 *  Licensed under the Apache License, Version 2.0 (the "License");
 *  you may not use this file except in compliance with the License.
 *  You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 *  Unless required by applicable law or agreed to in writing, software
 *  distributed under the License is distributed on an "AS IS" BASIS,
 *  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 *  See the License for the specific language governing permissions and
 *  limitations under the License.
 */


#include <Python.h>
#include "structmember.h"

#include "c.h"

static void t_values_dealloc(t_values *self);
static int t_values_traverse(t_values *self, visitproc visit, void *arg);
static int t_values_clear(t_values *self);
static PyObject *t_values_new(PyTypeObject *type,
                              PyObject *args, PyObject *kwds);
static int t_values_init(t_values *self, PyObject *args, PyObject *kwds);

static Py_ssize_t t_values_dict_length(t_values *self);
static int t_values_dict_contains(t_values *self, PyObject *key);
static PyObject *t_values_dict_get(t_values *self, PyObject *key);
static int t_values_dict_set(t_values *self, PyObject *key, PyObject *value);

static PyObject *t_values_get(t_values *self, PyObject *args);
static PyObject *t_values_keys(t_values *self, PyObject *arg);
static PyObject *t_values_items(t_values *self, PyObject *arg);
static PyObject *t_values_copy(t_values *self, PyObject *arg);
static PyObject *t_values__isReadOnly(t_values *self, PyObject *key);
static PyObject *t_values__isTransient(t_values *self, PyObject *key);
static PyObject *t_values__setTransient(t_values *self, PyObject *key);
static PyObject *t_values__clearTransient(t_values *self, PyObject *key);
static PyObject *t_values__clearDirtyAgain(t_values *self, PyObject *key);
static PyObject *t_values__isDirty(t_values *self, PyObject *key);
static PyObject *t_values__isDirtyAgain(t_values *self, PyObject *key);
static PyObject *t_values__clearDirties(t_values *self, PyObject *args);
static PyObject *t_values__getDirties(t_values *self, PyObject *args);

static PyObject *t_values__getDict(t_values *self, void *data);
static PyObject *t_values__getItem(t_values *self, void *data);
static int t_values__setItem(t_values *self, PyObject *item, void *data);

static PyObject *_setOwner_NAME;
static PyObject *_clearDirties_NAME;


static PyMemberDef t_values_members[] = {
    { "_flags", T_OBJECT, offsetof(t_values, flags), 0, "" },
    { "_ref", T_OBJECT, offsetof(t_values, ref), 0, "" },
    { NULL, 0, 0, 0, NULL }
};

static PyMethodDef t_values_methods[] = {
    { "get", (PyCFunction) t_values_get, METH_VARARGS, "" },
    { "keys", (PyCFunction) t_values_keys, METH_NOARGS, "" },
    { "items", (PyCFunction) t_values_items, METH_NOARGS, "" },
    { "copy", (PyCFunction) t_values_copy, METH_NOARGS, "" },
    { "_isReadOnly", (PyCFunction) t_values__isReadOnly, METH_O, "" },
    { "_isTransient", (PyCFunction) t_values__isTransient, METH_O, "" },
    { "_setTransient", (PyCFunction) t_values__setTransient, METH_O, "" },
    { "_clearTransient", (PyCFunction) t_values__clearTransient, METH_O, "" },
    { "_clearDirtyAgain", (PyCFunction) t_values__clearDirtyAgain, METH_O, "" },
    { "_isDirty", (PyCFunction) t_values__isDirty, METH_O, "" },
    { "_isDirtyAgain", (PyCFunction) t_values__isDirtyAgain, METH_O, "" },
    { "_setDirty", (PyCFunction) t_values__setDirty, METH_O, "" },
    { "_clearDirties", (PyCFunction) t_values__clearDirties, METH_VARARGS, "" },
    { "_getDirties", (PyCFunction) t_values__getDirties, METH_VARARGS, "" },
    { NULL, NULL, 0, NULL }
};

static PyGetSetDef t_values_properties[] = {
    { "_item",
      (getter) t_values__getItem,
      (setter) t_values__setItem,
      "", NULL },
    { "_dict",
      (getter) t_values__getDict,
      NULL, "", NULL },
    { NULL, NULL, NULL, NULL, NULL }
};

static PySequenceMethods t_values_as_sequence = {
    (lenfunc) t_values_dict_length,       /* sq_length */
    0,                                    /* sq_concat */
    0,                                    /* sq_repeat */
    0,                                    /* sq_item */
    0,                                    /* sq_slice */
    0,                                    /* sq_ass_item */
    0,                                    /* sq_ass_slice */
    (objobjproc) t_values_dict_contains,  /* sq_contains */
    0,                                    /* sq_inplace_concat */
    0,                                    /* sq_inplace_repeat */
};

static PyMappingMethods t_values_as_mapping = {
    (lenfunc) t_values_dict_length,
    (binaryfunc) t_values_dict_get,
    (objobjargproc) t_values_dict_set
};

static PyTypeObject ValuesType = {
    PyObject_HEAD_INIT(NULL)
    0,                                         /* ob_size */
    "chandlerdb.item.c.CValues",               /* tp_name */
    sizeof(t_values),                          /* tp_basicsize */
    0,                                         /* tp_itemsize */
    (destructor)t_values_dealloc,              /* tp_dealloc */
    0,                                         /* tp_print */
    0,                                         /* tp_getattr */
    0,                                         /* tp_setattr */
    0,                                         /* tp_compare */
    0,                                         /* tp_repr */
    0,                                         /* tp_as_number */
    &t_values_as_sequence,                     /* tp_as_sequence */
    &t_values_as_mapping,                      /* tp_as_mapping */
    0,                                         /* tp_hash  */
    0,                                         /* tp_call */
    0,                                         /* tp_str */
    0,                                         /* tp_getattro */
    0,                                         /* tp_setattro */
    0,                                         /* tp_as_buffer */
    (Py_TPFLAGS_DEFAULT |
     Py_TPFLAGS_BASETYPE |
     Py_TPFLAGS_HAVE_GC),                      /* tp_flags */
    "C Value type",                            /* tp_doc */
    (traverseproc)t_values_traverse,           /* tp_traverse */
    (inquiry)t_values_clear,                   /* tp_clear */
    0,                                         /* tp_richcompare */
    0,                                         /* tp_weaklistoffset */
    0,                                         /* tp_iter */
    0,                                         /* tp_iternext */
    t_values_methods,                          /* tp_methods */
    t_values_members,                          /* tp_members */
    t_values_properties,                       /* tp_getset */
    0,                                         /* tp_base */
    0,                                         /* tp_dict */
    0,                                         /* tp_descr_get */
    0,                                         /* tp_descr_set */
    0,                                         /* tp_dictoffset */
    (initproc)t_values_init,                   /* tp_init */
    0,                                         /* tp_alloc */
    (newfunc)t_values_new,                     /* tp_new */
};


static void t_values_dealloc(t_values *self)
{
    t_values_clear(self);
    self->ob_type->tp_free((PyObject *) self);
}

static int t_values_traverse(t_values *self, visitproc visit, void *arg)
{
    Py_VISIT(self->ref);
    Py_VISIT(self->dict);
    Py_VISIT(self->flags);

    return 0;
}

static int t_values_clear(t_values *self)
{
    Py_CLEAR(self->ref);
    Py_CLEAR(self->dict);
    Py_CLEAR(self->flags);

    return 0;
}

static PyObject *t_values_new(PyTypeObject *type,
                              PyObject *args, PyObject *kwds)
{
    t_values *self = (t_values *) type->tp_alloc(type, 0);

    if (self)
    {
        self->ref = NULL;
        self->dict = PyDict_New();
        self->flags = Nil; Py_INCREF(Nil);
    }

    return (PyObject *) self;
}

static int t_values_init(t_values *self, PyObject *args, PyObject *kwds)
{
    return 0;
}

static PyObject *t_values_copy(t_values *self, PyObject *args)
{
    PyTypeObject *type = self->ob_type;
    t_values *copy = (t_values *) type->tp_alloc(type, 0);

    if (copy)
    {
        copy->ref = NULL;
        copy->dict = PyDict_Copy(self->dict);
        copy->flags = Nil; Py_INCREF(Nil);
    }

    return (PyObject *) copy;
}

static Py_ssize_t t_values_dict_length(t_values *self)
{
    return PyDict_Size(self->dict);
}

static int t_values_dict_contains(t_values *self, PyObject *key)
{
    return PyDict_Contains(self->dict, key);
}

static PyObject *t_values_dict_get(t_values *self, PyObject *key)
{
    PyObject *value = PyDict_GetItem(self->dict, key);

    if (value)
    {
        if (value->ob_type == ItemRef)
            value = PyObject_Call(value, NULL, NULL);
        else
            Py_INCREF(value);

        return value;
    }

    PyErr_SetObject(PyExc_KeyError, key);
    return NULL;
}

static int t_values_dict_set(t_values *self, PyObject *key, PyObject *value)
{
    if (self->ref != NULL)
    {
        PyObject *oldValue = PyDict_GetItem(self->dict, key);

        if (oldValue == value)
            return 0;

        if (oldValue != NULL && PyObject_TypeCheck(oldValue, ItemValue))
        {
            PyObject *result =
                PyObject_CallMethodObjArgs(oldValue, _setOwner_NAME,
                                           Py_None, Py_None, NULL);

            if (!result)
                return -1;

            Py_DECREF(result);
        }
    }

    if (!value)
        return PyDict_DelItem(self->dict, key);
    else if (PyObject_TypeCheck(value, CItem))
        return PyDict_SetItem(self->dict, key,
                              (PyObject *) ((t_item *) value)->ref);
    else
        return PyDict_SetItem(self->dict, key, value);
}

static PyObject *t_values_get(t_values *self, PyObject *args)
{
    PyObject *key, *defaultValue = Py_None;

    if (!PyArg_ParseTuple(args, "O|O", &key, &defaultValue))
        return NULL;
    else
    {
        PyObject *value = PyDict_GetItem(self->dict, key);

        if (!value)
        {
            value = defaultValue;
            Py_INCREF(value);
        }
        else if (value->ob_type == ItemRef)
            value = PyObject_Call(value, NULL, NULL);
        else
            Py_INCREF(value);

        return value;
    }
}

static PyObject *t_values_keys(t_values *self, PyObject *arg)
{
    return PyDict_Keys(self->dict);
}

static PyObject *t_values_items(t_values *self, PyObject *arg)
{
    return PyDict_Items(self->dict);
}


static PyObject *is_bit_set(t_values *self, PyObject *key, int bit)
{
    if (self->flags != Nil)
    {
        PyObject *flag = PyDict_GetItem(self->flags, key);

        if (flag != NULL && PyInt_AsLong(flag) & bit)
            Py_RETURN_TRUE;
    }

    Py_RETURN_FALSE;
}

static PyObject *set_bit(t_values *self, PyObject *key, int bit)
{
    PyObject *flag;

    if (self->flags != Nil)
    {
        flag = PyDict_GetItem(self->flags, key);

        if (flag != NULL)
            flag = PyInt_FromLong(PyInt_AsLong(flag) | bit);
        else
            flag = PyInt_FromLong(bit);
    }
    else
    {
        Py_DECREF(self->flags);
        self->flags = PyDict_New();
        flag = PyInt_FromLong(bit);
    }

    PyDict_SetItem(self->flags, key, flag);

    return flag;
}

static PyObject *clear_bit(t_values *self, PyObject *key, int bit)
{
    if (self->flags != Nil)
    {
        PyObject *flags = PyDict_GetItem(self->flags, key);

        if (flags != NULL)
        {
            flags = PyInt_FromLong(PyInt_AsLong(flags) & ~bit);
            PyDict_SetItem(self->flags, key, flags);

            return flags;
        }
    }

    return PyInt_FromLong(0);
}

static PyObject *t_values__isReadOnly(t_values *self, PyObject *key)
{
    return is_bit_set(self, key, V_READONLY);
}

static PyObject *t_values__isTransient(t_values *self, PyObject *key)
{
    return is_bit_set(self, key, V_TRANSIENT);
}

static PyObject *t_values__isDirty(t_values *self, PyObject *key)
{
    return is_bit_set(self, key, V_DIRTY);
}

static PyObject *t_values__isDirtyAgain(t_values *self, PyObject *key)
{
    return is_bit_set(self, key, V_DIRTYAGAIN);
}

static PyObject *t_values__setTransient(t_values *self, PyObject *key)
{
    return set_bit(self, key, V_TRANSIENT);
}

PyObject *t_values__setDirty(t_values *self, PyObject *key)
{
    return set_bit(self, key, V_DIRTY | V_DIRTYAGAIN);
}

static PyObject *t_values__clearTransient(t_values *self, PyObject *key)
{
    return clear_bit(self, key, V_TRANSIENT);
}

static PyObject *t_values__clearDirtyAgain(t_values *self, PyObject *key)
{
    return clear_bit(self, key, V_DIRTYAGAIN);
}

static int _t_values__clearValueDirties(t_values *self, PyObject *value)
{
    PyObject *method = PyObject_GetAttr((PyObject *) value->ob_type,
                                        _clearDirties_NAME);

    if (PyCallable_Check(method))
    {
        PyObject *args = PyTuple_Pack(1, value);
        PyObject *result = PyObject_Call(method, args, NULL);

        Py_DECREF(args);
        Py_DECREF(method);

        if (result)
            Py_DECREF(result);
        else
            return -1;
    }
    else
        PyErr_Clear();

    return 0;
}

static PyObject *t_values__clearDirties(t_values *self, PyObject *args)
{
    int isNew = self->ref && self->ref->item->status & NEW;
    PyObject *key, *value, *flags;
    Py_ssize_t pos;
    int again = 0;

    if (!PyArg_ParseTuple(args, "|i", &again))
        return NULL;

    if (self->flags != Nil)
    {    
        pos = 0;
        while (PyDict_Next(self->flags, &pos, &key, &flags)) {
            unsigned int f = PyInt_AS_LONG(flags);

            if (again)
            {
                if (f & V_DIRTYAGAIN)
                {
                    f &= ~V_DIRTYAGAIN;
                    flags = PyInt_FromLong(f);
                    PyDict_SetItem(self->flags, key, flags);
                    Py_DECREF(flags);
                }
            }
            else if (f & V_DIRTY)
            {
                f &= ~(V_DIRTY | V_DIRTYAGAIN);
                flags = PyInt_FromLong(f);
                PyDict_SetItem(self->flags, key, flags);
                Py_DECREF(flags);

                if (!isNew)
                {
                    value = PyDict_GetItem(self->dict, key);
                    if (value && _t_values__clearValueDirties(self, value) < 0)
                        return NULL;
                }
            }
        }
    }
     
    /* when item is NEW, all values are dirty and thus are not flagged */
    if (isNew && !again)
    {
        pos = 0;
        while (PyDict_Next(self->dict, &pos, &key, &value))
            if (_t_values__clearValueDirties(self, value) < 0)
                return NULL;
    }

    Py_RETURN_NONE;
}

static PyObject *t_values__getDirties(t_values *self, PyObject *args)
{
    PyObject *key, *value, *dirties;
    Py_ssize_t pos = 0;
    int again = 0;

    if (!PyArg_ParseTuple(args, "|i", &again))
        return NULL;

    dirties = PyList_New(0);

    if (again)
        while (PyDict_Next(self->flags, &pos, &key, &value)) {
            int flags = PyInt_AS_LONG(value);

            if (flags & V_DIRTYAGAIN)
            {
                PyList_Append(dirties, key);

                flags &= ~V_DIRTYAGAIN;
                value = PyInt_FromLong(flags);
                PyDict_SetItem(self->flags, key, value);
                Py_DECREF(value);
            }
        }
    else
        while (PyDict_Next(self->flags, &pos, &key, &value)) {
            int flags = PyInt_AS_LONG(value);

            if (flags & V_DIRTY)
                PyList_Append(dirties, key);
        }

    return dirties;
}


/* _dict property */

static PyObject *t_values__getDict(t_values *self, void *data)
{
    PyObject *dict = self->dict;

    Py_INCREF(dict);
    return dict;
}

/* _item property */

static PyObject *t_values__getItem(t_values *self, void *data)
{
    t_itemref *ref = self->ref;

    if (ref == NULL)
        Py_RETURN_NONE;

    if (!ref->item)
    {
        PyErr_SetString(PyExc_AssertionError, "values._getItem(): no item");
        return NULL;
    }

    Py_INCREF(ref->item);
    return (PyObject *) ref->item;
}

static int t_values__setItem(t_values *self, PyObject *item, void *data)
{
    if (!item || item == Py_None)
    {
        Py_XDECREF(self->ref);
        self->ref = NULL;
        
        return 0;
    }

    if (PyObject_TypeCheck(item, CItem))
    {
        t_itemref *ref = ((t_item *) item)->ref;

        Py_XINCREF(ref);
        Py_XDECREF(self->ref);
        self->ref = ref;

        return 0;
    }

    PyErr_SetObject(PyExc_TypeError, item);
    return -1;
}


void _init_values(PyObject *m)
{
    if (PyType_Ready(&ValuesType) >= 0)
    {
        if (m)
        {
            PyObject *dict = ValuesType.tp_dict;

            Py_INCREF(&ValuesType);
            PyModule_AddObject(m, "CValues", (PyObject *) &ValuesType);
            CValues = &ValuesType;

            PyDict_SetItemString_Int(dict, "READONLY", V_READONLY);
            PyDict_SetItemString_Int(dict, "TOINDEX", V_TOINDEX);
            PyDict_SetItemString_Int(dict, "DIRTY", V_DIRTY);
            PyDict_SetItemString_Int(dict, "DIRTYAGAIN", V_DIRTYAGAIN);
            PyDict_SetItemString_Int(dict, "TRANSIENT", V_TRANSIENT);
            PyDict_SetItemString_Int(dict, "SAVEMASK", V_SAVEMASK);
            PyDict_SetItemString_Int(dict, "COPYMASK", V_COPYMASK);

            _setOwner_NAME = PyString_FromString("_setOwner");
            _clearDirties_NAME = PyString_FromString("_clearDirties");
        }
    }
}
