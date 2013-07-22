typedef char* CharStar;
typedef void* VoidStar;
typedef const char* ConstCharStar;
typedef const void* ConstVoidStar;

/**
 * Layout a list of strings into an array of pointers to the C-style strings.
 */
char** layout_argv(PyObject *list) {
	if (!PyList_Check(list)) {
		PyErr_SetString(PyExc_TypeError, "You must provide a list.");
		return NULL;
	}
	Py_ssize_t size = PyList_Size(list);
	Py_ssize_t i;
	PyObject* tmp;
	char** argv = (char**) malloc(sizeof(char*) * (size + 1));
	if (!argv) {
		PyErr_NoMemory();
		return NULL;
	}
	for (i = 0; i < size; ++i) {
		tmp = PyList_GetItem(list, i);
		if (!tmp) {
			free(argv);
			return NULL;
		}
		argv[i] = PyString_AsString(tmp);
		if (!argv[i]) {
			free(argv);
			return NULL;
		}
	}
	argv[size] = 0;
	return argv;
}

/**
 * Clean up the above function.
 */
void layout_argv_cleanup(char** argv) {
	free(argv);
}

/**
 * Wrap a Python callback for MRNet's event callback system.
 */
void _wrap_EventCallback(MRN::Event* e, void* data) {
	// This lets us check if threads have been initialized, and if not, we don't
	// use the locking API.
	int threads_inited = PyEval_ThreadsInitialized();
	PyGILState_STATE gstate;
	if (threads_inited) {
		gstate = PyGILState_Ensure();
	}
	PyObject* callback = (PyObject*) data;
	PyObject* ret = PyObject_CallFunction(callback, NULL);
	if (ret == NULL) {
	    // There was some sort of error. This is really ugly.
	    exit(1);
	}
	// Discard the reference to the result.
	Py_DECREF(ret);
	if (threads_inited) {
		PyGILState_Release(gstate);
	}
}
