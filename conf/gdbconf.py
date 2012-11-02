import lmonconf

# Correctly set the path to load MRNet.
import sys
sys.path.append("/usr/gapps/pgdb/chaos_5_x86_64_ib/lib/python2.6/site-packages")

# The binary for the backend daemons.
backend_bin = "python"
# The list of arguments to give to the backend daemons.
backend_args = ["/usr/gapps/pgdb/chaos_5_x86_64_ib/pgdb/gdbbe.py"]
# Environment variables to set in the front-end and back-end.
environ = dict(lmonconf.lmon_environ)
environ["XPLAT_RSH"] = "rsh"
#environ["MRNET_COMM_PATH"] = "/usr/local/tools/mrnet-3.1.0/bin/mrnet_commnode"
#environ["LD_LIBRARY_PATH"] = "/usr/local/tools/mrnet-3.1.0/lib"
environ["MRNET_COMM_PATH"] = "/collab/usr/global/tools/mrnet/chaos_5_x86_64_ib/mrnet-4.0.0/bin/mrnet_commnode"
environ["LD_LIBRARY_PATH"] = "/collab/usr/global/tools/mrnet/chaos_5_x86_64_ib/mrnet-4.0.0/lib"
# The path to the topology file for MRNet.
topology_path = "."
# The path to the GDB init file to use.
gdb_init_path = "/usr/gapps/pgdb/chaos_5_x86_64_ib/pgdb/gdbinit"
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
# The maximum length of a message before it is split into smaller messages for transmission over MRnet.
multi_len = 10240
