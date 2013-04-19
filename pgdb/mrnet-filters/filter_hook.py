"""Python filter hook for record aggregation."""

# Ensure paths are set correctly.
import sys
sys.path.append("/home/ndryden/PGDB/pgdb/src")
sys.path.append("/home/ndryden/lib/python2.7/site-packages")
import cPickle
from mi.gdbmiarec import *
from gdb_shared import *

def filter_hook(packet_list):
    """Called through MRNet filters. Given a list of messages of lists of arecs."""
    msg_list = map(cPickle.loads, packet_list)
    # Compute earliest sent time, if messages have them.
    # Performance must be enabled globally, so only check first message.
    new_time = None
    if hasattr(msg_list[0], '_send_time'):
        new_time = min(msg_list, key = lambda x: x._send_time)
        new_time = new_time._send_time
    arec_list = map(lambda x: x.record, msg_list)
    new_list = arec_list.pop(0)
    for l in arec_list:
        new_list = combine_aggregation_lists(new_list, l)
    msg = GDBMessage(OUT_MSG, record = new_list)
    if new_time:
        msg._send_time = new_time
    return cPickle.dumps(msg, 0)
