import sys, os, socket, time, cPickle, inspect
from mrnet.mrnet import *

class NodeInfo:
    def __init__(self, mrnrank, host, port, parent, be_rank):
        self.mrnrank = mrnrank
        self.host = host
        self.port = port
        self.parent = parent
        self.be_rank = be_rank

    def __str__(self):
        return "{0} {1} {2} {3} {4}".format(self.mrnrank, self.host,
                                            self.port, self.parent,
                                            self.be_rank)

    def __repr__(self):
        return "<" + self.__str__() + ">"

MSG_TAG = 3141
DIE_MSG = 0
QUIT_MSG = 1
CMD_MSG = 2
OUT_MSG = 3
FILTER_MSG = 4
UNFILTER_MSG = 5
HELLO_MSG = 6
VARPRINT_MSG = 7
VARPRINT_RES_MSG = 8
MULTI_MSG = 9
MULTI_PAYLOAD_MSG = 10
KILL_MSG = 11

class GDBMessage:
    """A simple class for transmitting messages and related information."""

    def __init__(self, msg_type, **kwargs):
        """Set up the message.

        msg_type is the type of the message; see above constants.
        All additional keyword arguments are set as attributes for message-specific use.

        """
        self.msg_type = msg_type
        for k, v in kwargs.items():
            setattr(self, k, v)

    def __str__(self):
        """Produce a string representation of the message.

        Prints the message type and then the keys and values.

        """
        s = ""
        members = inspect.getmembers(self, lambda x: not inspect.isroutine(x))
        for k, v in members:
            if k[0:2] != "__":
                # Keep out things like __doc__ and __module__.
                s += "{0} = {1}, ".format(k, v)
        return "GDBMessage: " + s[:-2]
