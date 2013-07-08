"""Common LaunchMON Python interface definitions.

This defines some useful things common to both the LaunchMON front- and back-end interfaces, as well
as things useful to things using this interface, such as exceptions and CTypes structures.

"""

from ctypes import *
import cPickle
# If we can't import from conf, see if it's in the current directory.
try:
    from conf import lmonconf
except ImportError:
    import lmonconf

class LMONException(Exception):
    """An error from LaunchMON.

    This is raised whenever a LaunchMON function returns an error code that is not one of:
    LMON_OK, LMON_YES, or LMON_NO.

    """
    def __init__(self, value):
        self.value = int(value)

    def __str__(self):
        if self.value < len(lmon_const_map):
            return lmon_const_map[self.value]
        else:
            return "Unknown ({0})".format(self.value)

    def print_lmon_error(self):
        """Print a short error message."""
        print "Caught LaunchMON error, code = {0} ({1})".format(self, self.value)

class MPIR_PROCDESC(Structure):
    """A CTypes structure for the MPIR_PROCDESC structure."""
    _fields_ = [("host_name", c_char_p),
                ("executable_name", c_char_p),
                ("pid", c_int)]

class MPIR_PROCDESC_EXT(Structure):
    """A CTypes structure for the MPIR_PROCDESC_EXT structure."""
    _fields_ = [("pd", MPIR_PROCDESC),
                ("mpirank", c_int)]

class lmon_daemon_env_t(Structure):
    """A CTypes structure for the lmon_daemon_env_t structure."""
    pass
lmon_daemon_env_t._fields_ = [("envName", c_char_p),
                              ("envValue", c_char_p),
                              ("next", POINTER(lmon_daemon_env_t))]

# The LaunchMON version number from the configuration.
LMON_VERSION = lmonconf.lmon_version
# LaunchMON constants, based on which version we're using.
if lmonconf.use_lmon_10:
    (LMON_OK, LMON_EINVAL, LMON_EBDARG, LMON_ELNCHR,
     LMON_EINIT, LMON_ESYS, LMON_ESUBCOM, LMON_ESUBSYNC,
     LMON_ETOUT, LMON_ENOMEM, LMON_ENCLLB, LMON_ECLLB,
     LMON_ENEGCB, LMON_ENOPLD, LMON_EBDMSG, LMON_EDUNAV,
     LMON_ETRUNC, LMON_EBUG, LMON_NOTIMPL, LMON_YES,
     LMON_NO) = map(int, xrange(21))
    lmon_const_map = [
        "LMON_OK",
        "LMON_EINVAL",
        "LMON_EDBARG",
        "LMON_ELNCHR",
        "LMON_EINIT",
        "LMON_ESYS",
        "LMON_ESUBCOM",
        "LMON_ESUBSYNC",
        "LMON_ETOUT",
        "LMON_ENOMEM",
        "LMON_ENCLLB",
        "LMON_ECLLB",
        "LMON_ENEGCB",
        "LMON_ENOPLD",
        "LMON_EBDMSG",
        "LMON_EDUNAV",
        "LMON_ETRUNC",
        "LMON_EBUG",
        "LMON_NOTIMPL",
        "LMON_YES",
        "LMON_NO"
    ]
else:
    (LMON_OK, LMON_EINVAL, LMON_EBDARG, LMON_ELNCHR,
     LMON_EINIT, LMON_ESYS, LMON_ESUBCOM, LMON_ETOUT,
     LMON_ENOMEM, LMON_ENCLLB, LMON_ECLLB, LMON_ENEGCB,
     LMON_ENOPLD, LMON_EBDMSG, LMON_EDUNAV, LMON_EBUG,
     LMON_YES, LMON_NO) = map(int, xrange(18))
    lmon_const_map = [
        "LMON_OK",
        "LMON_EINVAL",
        "LMON_EDBARG",
        "LMON_ELNCHR",
        "LMON_EINIT",
        "LMON_ESYS",
        "LMON_ESUBCOM",
        "LMON_ETOUT",
        "LMON_ENOMEM",
        "LMON_ENCLLB",
        "LMON_ECLLB",
        "LMON_ENEGCB",
        "LMON_ENOPLD",
        "LMON_EBDMSG",
        "LMON_EDUNAV",
        "LMON_EBUG",
        "LMON_YES",
        "LMON_NO"
    ]

def call(func, *args):
    """Call a LaunchMON function and handle raising exceptions.

    func is the function to call.
    args are expanded to the positional arguments to pass to func.

    The return code is returned if it is not an error.

    """
    rc = func(*args)
    if rc not in [LMON_OK, LMON_YES, LMON_NO]:
        raise LMONException(rc)
    return rc

def create_array(ctype, lis):
    """A helper function to lay out a CTypes array."""
    if len(lis):
        ar = ctype * len(lis)
        _lis = ar(*tuple(lis))
        return _lis
    else:
        return None

def udata_serialize(udata):
    """Serialize data into a CType."""
    # Must use protocol 0; the binary protocol appears to break ctypes somehow.
    return cast(c_char_p(cPickle.dumps(udata, 0)), c_void_p)

def udata_serialize_len(udata):
    """Unserialize data, returning the data and the length."""
    serialized = cPickle.dumps(udata, 0)
    return cast(c_char_p(serialized), c_void_p), len(serialized)

def udata_unserialize(udata):
    """Unserialize data."""
    return cPickle.loads(udata)

def pack(udata, msgbuf, msgbufmax, msgbuflen):
    """The pack callback for LaunchMON; see the relevant manpages."""
    udata_size = len(string_at(udata))
    if udata_size > msgbuflen:
        raise ValueError("LMon pack got data larger than the message buffer.")
    memmove(msgbuf, udata, udata_size)
    msgbuflen[0] = udata_size
    return 0

def unpack(udatabuf, udatabuflen, udata):
    """The unpack callback for LaunchMON; seel the relevant manpages."""
    memmove(udata, udatabuf, udatabuflen)
    return 0
