"""Python filter hook for record aggregation."""

# Need to specify the directory for PGDB.
import sys
sys.path.append("/home/ndryden/PGDB/pgdb/src")
from conf import gdbconf
gdbconf.set_path()
import cPickle
from mi.gdbmiarec import *
from gdb_shared import *

def filter_hook(packet_list):
    """PGDB deduplication filter for MRNet.

    This is invoked via a C filter called from MRNet.
    Messages with type OUT_MSG are merged into combined aggregated records.
    packet_list is a list of serialized packets provided by MRNet.
    These packets cannot be compressed.
    Returns a serialized list of packets to MRNet.

    """
    msg_list = map(cPickle.loads, packet_list)
    # Compute earliest sent time, if messages have them.
    # Performance must be enabled globally, so only check first message.
    new_time = None
    if hasattr(msg_list[0], '_send_time'):
        new_time = min(msg_list, key = lambda x: x._send_time)
        new_time = new_time._send_time
    packets = []
    record_msgs = []
    for msg in msg_list:
        # Only process messages of type OUT_MSG.
        if msg.msg_type == OUT_MSG:
            record_msgs.append(msg)
        else:
            packets.append(msg)
    if record_msgs:
        arec_list = map(lambda x: x.record, record_msgs)
        new_list = arec_list.pop(0)
        for l in arec_list:
            new_list = combine_aggregated_records(new_list + l)
        packets.append(GDBMessage(OUT_MSG, record = new_list))
    for i, msg in enumerate(packets):
        if new_time:
            msg._send_time = new_time
        packets[i] = cPickle.dumps(msg, 0)
    return packets
