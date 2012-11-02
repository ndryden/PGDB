"""A CTypes interface to the LaunchMON front-end library."""

from ctypes import *
import lmon

class LMON_fe(object):
    """An interface to the LaunchMON front-end library using CTypes.

    This loads the library, provides for type-checking of arguments, and handles some
    convenience things. See the LaunchMON manpages for additional information.

    """

    def __init__(self):
        """Initialize the LaunchMON front-end library."""
        self.lib = cdll.LoadLibrary(lmon.lmonconf.lmon_fe_lib)
        # Used for keeping callbacks alive.
        self.pack_cbs = {}
        self.unpack_cbs = {}
        self.pack_type = CFUNCTYPE(c_int, c_void_p, c_void_p, c_int, POINTER(c_int))
        self.unpack_type = CFUNCTYPE(c_int, c_void_p, c_int, c_void_p)
        # Set up argument types.
        self.lib.LMON_fe_init.argtypes = [c_int]
        self.lib.LMON_fe_createSession.argtypes = [POINTER(c_int)]
        self.lib.LMON_fe_attachAndSpawnDaemons.argtypes = [c_int, c_char_p, c_int,
                                                           c_char_p, POINTER(c_char_p),
                                                           c_void_p, c_void_p]
        self.lib.LMON_fe_launchAndSpawnDaemons.argtypes = [c_int, c_char_p, c_char_p,
                                                           POINTER(c_char_p), c_char_p,
                                                           POINTER(c_char_p), c_void_p,
                                                           c_void_p]
        self.lib.LMON_fe_regPackForFeToBe.argtypes = [c_int, self.pack_type]
        self.lib.LMON_fe_regUnpackForBeToFe.argtypes = [c_int, self.unpack_type]
        self.lib.LMON_fe_sendUsrDataBe.argtypes = [c_int, c_void_p]
        self.lib.LMON_fe_recvUsrDataBe.argtypes = [c_int, c_void_p]
        self.lib.LMON_fe_putToBeDaemonEnv.argtypes = [c_int, POINTER(lmon.lmon_daemon_env_t),
                                                      c_int]
        self.lib.LMON_fe_getProctableSize.argtypes = [c_int, POINTER(c_uint)]
        # We use c_void_p here because ctypes isn't good at resolving the multiple-pointers.
        self.lib.LMON_fe_getProctable.argtypes = [c_int, c_void_p,
                                                  POINTER(c_uint), c_uint]

    def init(self):
        """Invoke LMON_fe_init."""
        lmon.call(self.lib.LMON_fe_init, lmon.LMON_VERSION)

    def createSession(self):
        """Create and return a session handle with LMON_fe_createSession."""
        session = c_int()
        lmon.call(self.lib.LMON_fe_createSession, byref(session))
        return session.value

    def attachAndSpawnDaemons(self, session, hostname, pid, daemon, d_argv, febe_data, befe_data):
        """Invoke LMON_fe_attachAndSpawnDaemons. See the manpages. d_argv is a list. befe_data is the size of the desired buffer or None."""
        # Need a trailing null entry on the array.
        d_argv += [None]
        _d_argv = lmon.create_array(c_char_p, d_argv)
        if febe_data is not None:
            _febe_data = lmon.udata_serialize(febe_data)
        else:
            _febe_data = cast(None, c_void_p)
        buf = None
        if befe_data is not None:
            buf = create_string_buffer(befe_data)
            _befe_data = cast(buf, c_void_p)
        else:
            _befe_data = cast(None, c_void_p)
        lmon.call(self.lib.LMON_fe_attachAndSpawnDaemons, session, hostname, pid, daemon, _d_argv,
                  _febe_data, _befe_data)
        if befe_data:
            return lmon.udata_unserialize(buf.value)
        else:
            return None

    def launchAndSpawnDaemons(self, session, hostname, launcher, l_argv, daemon, d_argv, febe_data,
                              befe_data):
        """Invoke LMON_fe_launchAndSpawnDaemons."""
        # Need trailing null entries on the arrays.
        l_argv += [None]
        d_argv += [None]
        _l_argv = lmon.create_array(c_char_p, l_argv)
        _d_argv = lmon.create_array(c_char_p, d_argv)
        if febe_data is not None:
            _febe_data = lmon.udata_serialize(febe_data)
        else:
            _febe_data = cast(None, c_void_p)
        buf = None
        if befe_data is not None:
            buf = create_string_buffer(befe_data)
            _befe_data = cast(buf, c_void_p)
        else:
            _befe_data = cast(None, c_void_p)
        lmon.call(self.lib.LMON_fe_launchAndSpawnDaemons, session, hostname, launcher, _l_argv,
                  daemon, _d_argv, _febe_data, _befe_data)
        if befe_data:
            return lmon.udata_unserialize(buf.value)
        else:
            return None

    def regPackForFeToBe(self, session, callback):
        """Register a pack function with LMON_fe_regPackForFeToBe."""
        cb = self.pack_type(callback)
        self.pack_cbs[session] = cb
        lmon.call(self.lib.LMON_fe_regPackForFeToBe, session, cb)

    def regUnpackForBeToFe(self, session, callback):
        """Register an unpack function with LMON_fe_regUnpackForBeToFe."""
        cb = self.unpack_type(callback)
        self.unpack_cbs[session] = cb
        lmon.call(self.lib.LMON_fe_regUnpackForBeToFe, session, cb)

    def sendUsrDataBe(self, session, febe_data):
        """Send user data to the backend with LMON_fe_sendUsrDataBe (it is serialized)."""
        lmon.call(self.lib.LMON_fe_sendUsrDataBe, session, lmon.udata_serialize(febe_data))

    def recvUsrDataBe(self, session, buf_size):
        """Receive user data from the backend with LMON_fe_recvUsrDataBe (it is unserialized)."""
        befe_data = create_string_buffer(buf_size)
        lmon.call(self.lib.LMON_fe_recvUsrDataBe, session, cast(befe_data, c_void_p))
        return lmon.udata_unserialize(befe_data.raw)

    def putToBeDaemonEnv(self, session, environ):
        """Set up the backend environment with LMON_fe_putToBeDaemonEnv.

        Environ is a list of tuples of keys and values.

        """
        env_list_type = lmon.lmon_daemon_env_t * len(environ)
        env_list = env_list_type()
        for k, env_item in enumerate(environ):
            env_list[k].envName = env_item[0]
            env_list[k].envValue = env_item[1]
            if k < (len(environ) - 1):
                env_list[k].next = pointer(env_list[k + 1])
            else:
                env_list[k].next = None
        lmon.call(self.lib.LMON_fe_putToBeDaemonEnv, session, env_list, len(environ))

    def getProctableSize(self, session):
        """Return the size of the process table with LMON_fe_getProctableSize."""
        size = c_uint()
        lmon.call(self.lib.LMON_fe_getProctableSize, session, byref(size))
        return size.value

    def getProctable(self, session, maxsize):
        """Return the process table and its size with LMON_fe_getProctable."""
        proctab_type = lmon.MPIR_PROCDESC_EXT * maxsize
        proctab = proctab_type()
        size = c_uint()
        lmon.call(self.lib.LMON_fe_getProctable, session, byref(proctab), byref(size), c_uint(maxsize))
        return proctab, size.value
