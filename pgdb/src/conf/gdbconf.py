"""Base configuration file for PGDB."""

import sys
def set_path():
    """Set appropriate Python paths."""
    sys.path.append("/g/g21/dryden1/lib/python2.6/site-packages/")
set_path()

from lmon import lmonconf

mrnet_base = "/collab/usr/global/tools/mrnet/chaos_5_x86_64_ib/mrnet-4.0.0"
pgdb_path = "/g/g21/dryden1/pgdb/pgdb"

# The binary for the backend daemons.
backend_bin = "python"
# The list of arguments to give to the backend daemons.
backend_args = [pgdb_path + "/src/gdbbe.py"]
# Environment variables to set in the front-end and back-end.
environ = dict(lmonconf.lmon_environ)
environ["XPLAT_RSH"] = "rsh"
environ["MRNET_COMM_PATH"] = mrnet_base + "/bin/mrnet_commnode"
environ["LD_LIBRARY_PATH"] = mrnet_base + "/lib"
# The path to the GDB binary.
gdb_path = "gdb"
# The path to the topology file for MRNet.
topology_path = "."
# The path to the GDB init file to use.
gdb_init_path = pgdb_path + "/gdbinit"
# Whether to use pretty printing, raw printing, or both.
# Possible values are "yes", "no", or "both".
pretty_print = "yes"
# Whether to dump raw printing output to a file. False to not, otherwise the file.
import os
print_dump_file = "raw_dump_{0}".format(os.getpid())
# Varprint configuration options.
# The maximum depth to descend when printing an object.
varprint_max_depth = 3
# The maximum number of children of an object to consider unless explicitly printing the object.
# (Note, this is just children, not descendants.)
varprint_max_children = 60
# The branching factor to use when constructing the MRNet topology.
mrnet_branch_factor = 32
# The size of each topology broadcast, from the front-end to the back-end master, and the master to
# all the other backends.
topology_transmit_size = 32768
# Maximum length of a message before it is compressed.
compress_threshold = 10240
# The maximum length of a message before it is split into smaller messages for transmission over MRNet.
multi_len = 5242880
# A list of tuples of the form (path, function), where path is a path to an MRNet filter
# and function is the name of the filter function.
mrnet_filters = [(pgdb_path + "/mrnet-filters/arec_filter.so", "arec_filter")]
# Whether to enable collection of MRNet performance data or not.
mrnet_collect_perf_data = True
# Whether to write a DOT file of the topology. The path of the file if yes, None otherwise.
mrnet_topology_dot = "/home/ndryden/topo.dot"
# The length of history to keep.
history_length = 100
# Whether to load files using the SBD system.
use_sbd = True
# Path to the SBD shared library.
sbd_bin = pgdb_path + "/load_file.so"
# Size of shared memory the SBD uses, in bytes. Currently 32 MiB.
sbd_shmem_size = 33554432
