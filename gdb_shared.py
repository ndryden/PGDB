import sys, os, socket, time, cPickle
from mrnet.mrnet import *

class NodeInfo:
    def __init__(self, mrnrank, host, port, parent):
        self.mrnrank = mrnrank
        self.host = host
        self.port = port
        self.parent = parent

    def __str__(self):
        return "{0} {1} {2} {3}".format(self.mrnrank, self.host,
                                        self.port, self.parent)

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

    def __init__(self, msg_type, rank, **kwargs):
        """Set up the message.

        msg_type is the type of the message; see above constants.
        rank is the set of ranks to send this message to; see below.
        All additional keyword arguments are set as attributes for message-specific use.

        The rank parameter may be either -1 to indicate all ranks, or an instance of the Interval
        class containing the specified ranks, or a particular integer (only for OUT_MSG right now).

        """
        self.msg_type = msg_type
        self.rank = rank
        for k, v in kwargs.items():
            setattr(self, k, v)
