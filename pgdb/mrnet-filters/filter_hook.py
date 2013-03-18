"""Python filter hook for record aggregation."""

# Ensure paths are set correctly.
import sys
sys.path.append("/home/ndryden/PGDB/pgdb/src")
sys.path.append("/home/ndryden/lib/python2.7/site-packages")
import cPickle
from mi.gdbmiarec import *

def filter_hook(packet_list):
    """Called through MRNet filters. Given a list of lists of arecs."""
    data_list = map(cPickle.loads, packet_list)
    arec_list = data_list.pop(0)
    for rec in data_list:
        arec_list = combine_aggregation_lists(arec_list, rec)
    return cPickle.dumps(arec_list, 0)
    #return packet_list[0]
