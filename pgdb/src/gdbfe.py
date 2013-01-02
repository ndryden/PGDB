"""The front-end interface to PGDB.

This handles user input, deploying the network and remote debuggers, and everything else related to
this.

"""

import threading, thread
from collections import deque
from conf import gdbconf
from gdb_shared import *
from lmon.lmonfe import LMON_fe
from lmon import lmon
from mi.gdbmi_front import GDBMICmd
from mi.gdbmi_identifier import GDBMIRecordIdentifier
from mi.gdbmi_recordhandler import GDBMIRecordHandler
from mi.varobj import VariableObject, VariableObjectManager
from pprinter import GDBMIPrettyPrinter
from interval import Interval

class GDBFE (GDBMICmd):
    """The front-end to PGDB."""

    def init_lmon(self):
        """Initialize LaunchMON and deploy back-end daemons."""
        os.environ.update(gdbconf.environ)
        self.lmonfe = LMON_fe()
        self.lmonfe.init()
        self.lmon_session = self.lmonfe.createSession()
        self.lmonfe.putToBeDaemonEnv(self.lmon_session, gdbconf.environ.items())
        self.lmonfe.regPackForFeToBe(self.lmon_session, lmon.pack)
        self.lmonfe.regUnpackForBeToFe(self.lmon_session, lmon.unpack)
        if self.lmon_attach:
            self.lmonfe.attachAndSpawnDaemons(self.lmon_session,
                                              socket.getfqdn(),
                                              self.lmon_pid,
                                              gdbconf.backend_bin,
                                              gdbconf.backend_args,
                                              None, None)
        else:
            self.lmon_l_argv = [self.lmon_launcher] + self.lmon_l_argv
            self.lmonfe.launchAndSpawnDaemons(self.lmon_session,
                                              socket.getfqdn(),
                                              self.lmon_launcher,
                                              self.lmon_l_argv,
                                              gdbconf.backend_bin,
                                              gdbconf.backend_args,
                                              None, None)

        self.proctab_size = self.lmonfe.getProctableSize(self.lmon_session)
        self.proctab, unused = self.lmonfe.getProctable(self.lmon_session, self.proctab_size)

    def init_mrnet(self):
        """Initialize MRNet and send node information to back-end daemons."""
        self.node_joins = 0
        self.packet_stash = []
        self.multi_stash = []
        self.construct_topology()
        self.mrnet = MRN.Network.CreateNetworkFE(self.topo_path)
        #self.test_filter_id = self.mrnet.load_FilterFunc("/g/g21/dryden1/pgdb/mrnet-filters/test.so", "test")
        #if self.test_filter_id == -1:
        #    print "Loading filter function failed!"
        self.mrnet.register_EventCallback(MRN.Event.TOPOLOGY_EVENT,
                                          MRN.TopologyEvent.TOPOL_ADD_BE,
                                          self.node_joined_callback)
        self.mrnet.register_EventCallback(MRN.Event.TOPOLOGY_EVENT,
                                          MRN.TopologyEvent.TOPOL_REMOVE_NODE,
                                          self.node_removed_callback)
        self.send_node_info()

    def construct_topology(self):
        """Construct the topology we will use for the communication network."""
        branch_factor = gdbconf.mrnet_branch_factor
        hostlist = list(set(map(lambda x: x.pd.host_name, self.proctab)))
        cur_host = socket.gethostname()
        if cur_host in hostlist:
            # Prevent the front-end appearing twice.
            #hostlist.remove(cur_host)
            # For now, don't allow this. It breaks.
            print "Cannot have front-end on the same machine as back-end daemons."
            sys.exit(1)
        cur_parents = [cur_host] # Front end.
        self.topo_path = "{0}/topo_{1}".format(gdbconf.topology_path, os.getpid())
        fmt = "{0}:0"
        with open(self.topo_path, "w+") as topo_file:
            while hostlist:
                new_parents = []
                for parent in cur_parents:
                    children = hostlist[:branch_factor]
                    new_parents += children
                    del hostlist[:branch_factor]
                    if children:
                        topo_file.write(fmt.format(parent) + " => " + 
                                        " ".join(map(lambda x: fmt.format(x), children)) + " ;\n")
                cur_parents = new_parents

    def send_node_info(self):
        """Send node information to the back-end daemons."""
        self.topology = self.mrnet.get_NetworkTopology()
        self.leaves = self.topology.get_Leaves()
        self.mrn_parents = self.topology.get_ParentNodes()
        node_info = {}
        for leaf in self.leaves:
            node_info[leaf.get_Rank()] = NodeInfo(leaf.get_Rank(),
                                                  leaf.get_HostName(),
                                                  leaf.get_Port(),
                                                  leaf.get_Parent())
        local_rank = self.mrnet.get_LocalRank()
        for parent in self.mrn_parents:
            if parent.get_Rank() != local_rank:
                node_info[parent.get_Rank()] = NodeInfo(parent.get_Rank(),
                                                        parent.get_HostName(),
                                                        parent.get_Port(),
                                                        parent.get_Parent())
            else:
                # Special case for the root, as otherwise we would segfault.
                node_info[local_rank] = NodeInfo(local_rank, parent.get_HostName(),
                                                 parent.get_Port(), -1)
        self.lmonfe.sendUsrDataBe(self.lmon_session, node_info)
        self.network_size = len(node_info) - 1

    def create_rank_mapping(self):
        """Create the rank mappings we use in functions, for going from MRNet ranks to MPI ranks."""
        self.mpirank_to_mrnrank = {}
        self.mpiranks = []
        hostname_to_mrnrank = {}
        for ep in self.broadcast_comm.get_EndPoints():
            hostname_to_mrnrank[socket.getfqdn(ep.get_HostName())] = ep.get_Rank()
        hostname_to_mpirank = {}
        for proc in self.proctab:
            self.mpiranks.append(proc.mpirank)
            self.mpirank_to_mrnrank[proc.mpirank] = hostname_to_mrnrank[socket.getfqdn(proc.pd.host_name)]
        self.all_ranks = Interval(lis = self.mpiranks)

    def node_joined_callback(self):
        """An MRNet callback invoked whenever a backend node joins."""
        self.node_joins += 1

    def node_removed_callback(self):
        """An MRNet callback invoked whenever a backend node leaves."""
        self.num_nodes -= 1
        if self.num_nodes == 0:
            print "All nodes have exited."
            self.quit = True

    def get_gdb_cmds(self):
        """Receive the GDB commands from the back-end master."""
        self.gdb_cmds = self.lmonfe.recvUsrDataBe(self.lmon_session, 10240)

    def mrnet_stream_send(self, stream, msg_type, **kwargs):
        """Send a constructed GDBMessage on a given MRNet stream."""
        # Our rank isn't helpful.
        self.mrnet_stream_send_msg(stream, GDBMessage(msg_type, Interval(lis = []), **kwargs))

    def mrnet_stream_send_msg(self, stream, msg):
        """Send a given GDBMessage on a given MRNet stream."""
        msg = cPickle.dumps(msg, 0)
        if stream.send(MSG_TAG, "%s", msg) == -1:
            print "Terminal network failure on send."
            sys.exit(1)

    def mrnet_recv(self, blocking = True):
        """Receive and unserialize data from MRNet."""
        ret, tag, packet, stream = self.mrnet.recv(blocking)
        if ret == -1:
            print "Terminal network failure on recv."
            sys.exit(1)
        if ret == 0:
            return None, None
        ret, serialized = packet.get().unpack("%s")
        if ret == -1:
            print "Could not unpack packet."
            sys.exit(1)
        msg = cPickle.loads(serialized)
        # We need to keep Python from garbage-collecting these.
        self.packet_stash.append(packet)
        return msg, stream

    def init_mrnet_streams(self):
        """Initialize some basic MRNet streams and send the HELLO message."""
        self.broadcast_comm = self.mrnet.get_BroadcastCommunicator()
        self.broadcast_stream = self.mrnet.new_Stream(self.broadcast_comm, 0, 0, 0)
        self.mrnet_stream_send(self.broadcast_stream, HELLO_MSG)

    def init_handlers(self):
        """Initialize the message handlers and the record handler."""
        # Set up message handlers.
        self.msg_handlers = {
            DIE_MSG: self.die_handler,
            QUIT_MSG: self.quit_handler,
            OUT_MSG: self.out_handler,
            VARPRINT_RES_MSG: self.varprint_res_handler,
            MULTI_MSG: self.multi_handler
            }
        # Now record handlers.
        self.record_handler = GDBMIRecordHandler(self.identifier)

    def remote_init(self):
        """Initialize things related to the remote communication and back-end daemons."""
        self.init_lmon()
        self.init_mrnet()
        self.wait_for_nodes()
        self.init_mrnet_streams()
        self.create_rank_mapping()
        self.get_gdb_cmds()
        self.identifier = GDBMIRecordIdentifier()
        self.varobjs = {}
        for rank in self.mpiranks:
            self.varobjs[rank] = VariableObjectManager()
        self.init_handlers()
        self.pprinter = GDBMIPrettyPrinter(self.identifier)
        self.current_token = 0
        self.msg_queue = deque([])
        self.msg_queue_lock = threading.RLock()
        self.sleep_time = 0.1
        self.blocks = []
        try:
            self.blocks += gdbconf.default_blocks
        except AttributeError: pass

    def __init__(self):
        """Initialize some local things; the remote initialization must be done seperately."""
        GDBMICmd.__init__(self)
        self.quit = False
        self.is_shutdown = False
        # Need to disable readline.
        self.completekey = None

    def wait_for_nodes(self):
        """Wait until all nodes have joined the network."""
        while self.node_joins != self.network_size: pass
        self.num_nodes = self.node_joins

    def parse_args(self):
        """Parse the command-line arguments and set appropriate variables."""
        # Optparse unfortunately doesn't work here.
        self.lmon_attach = None
        for i in range(1, len(sys.argv)):
            if sys.argv[i] == "-p" or sys.argv[i] == "--pid":
                self.lmon_attach = True
                if len(sys.argv) == i:
                    print "Must provide a PID with {0}.".format(sys.argv[i])
                    sys.exit(0)
                try:
                    self.lmon_pid = int(sys.argv[i + 1])
                except ValueError:
                    print "Must provide a valid PID."
                    sys.exit(0)
                i += 1
            elif sys.argv[i] == "--launcher":
                if len(sys.argv) == i:
                    print "Must provide a launcher with --launcher."
                    sys.exit(0)
                self.lmon_launcher = sys.argv[i + 1]
                i += 1
            elif sys.argv[i] == "-a":
                if not hasattr(self, "lmon_launcher"):
                    self.lmon_launcher = "srun"
                self.lmon_attach = False
                self.lmon_l_argv = sys.argv[i + 1:]
                break
        if self.lmon_attach is None:
            print "Arguments: (one of -p/--pid and -a is required)"
            print "-p, --pid <pid>: attach to srun process <pid>"
            print "-a <options>: pass <options> verbatim to the resource manager for launching."
            print "--launcher <launcher>: use binary <launcher> to launch."
            sys.exit(0)

    def shutdown(self):
        """Shut down the network if not already shut down."""
        if not self.is_shutdown:
            try:
                del self.mrnet
            except AttributeError: pass
            self.is_shutdown = True

    def __del__(self):
        """Invoke shutdown()."""
        self.shutdown()

    def msg_rank_to_list(self, msg_rank):
        """Convert a rank to a list of ranks."""
        if isinstance(msg_rank, int):
            return [msg_rank]
        return msg_rank.members()

    def die_handler(self, msg):
        """Handle a die message. Presently does nothing."""
        pass

    def quit_handler(self, msg):
        """Handle a die message. Presently does nothing."""
        pass

    def out_handler(self, msg):
        """Handle an out message by pretty-printing the record."""
        if msg.rank not in self.blocks:
            if self.record_handler.handle(msg.record, rank = msg.rank):
                self.pprinter.pretty_print(msg.record, msg.rank)

    def varprint_res_handler(self, msg):
        """Handle a varprint result message by pretty-printing the variable objects."""
        if msg.err:
            print "[{0}] {1}".format(msg.rank, msg.msg)
        elif msg.varobj:
            self.varobjs[msg.rank].add_var_obj(msg.varobj)
            print self.pprinter.varobj_pretty_print(msg.varobj, tag = msg.rank)[:-1]
        else:
            print "[{0}] Received a bad varobj!".format(msg.rank)

    def multi_handler(self, msg):
        """Handle receiving a multi-part message."""
        # msg.num - number of messages to expect.
        # Receive a bunch of MULTI_PAYLOAD_MSGs. Each one has a "payload"
        # that we put together to form the original message.
        # Other messages are handled normally.
        # We check the multi-stash in case other mutli-message commands received our data, too.
        payload = ""
        counter = 0
        while counter != msg.num:
            multi_msg = None
            for i in range(0, len(self.multi_stash)):
                multi = self.multi_stash[i]
                if multi.rank == msg.rank:
                    multi_msg = multi
                    del self.multi_stash[i]
                    # Must break here or we'll get undefined results.
                    break
            while not multi_msg:
                recvd, stream = self.mrnet_recv()
                if recvd is not None:
                    if recvd.msg_type == MULTI_PAYLOAD_MSG:
                        if recvd.rank == msg.rank:
                            multi_msg = recvd
                        else:
                            self.multi_stash.append(multi_msg)
                    else:
                        self.handle_msg(recvd)
            payload += multi_msg.payload
            counter += 1
        final_msg = cPickle.loads(payload)
        self.handle_msg(final_msg)

    def parse_filter_spec(self, spec):
        """Parse a filter specification into a record type and class."""
        split = spec.lower().split()
        record_type = split[0]
        record_class = None
        if len(split) > 1:
            record_class = split[1]
        return record_type, record_class

    def do_filter(self, cmd, targets = None):
        """Tell the back-end daemons to filter something."""
        record_type, record_class = self.parse_filter_spec(cmd)
        self.queue_msg(GDBMessage(FILTER_MSG, self.all_ranks, filter_type = record_type,
                                  filter_class = record_class))

    def do_unfilter(self, cmd, targets = None):
        """Tell the back-end daemons to unfilter something."""
        record_type, record_class = self.parse_filter_spec(cmd)
        self.queue_msg(GDBMessage(UNFILTER_MSG, self.all_ranks, filter_type = record_type,
                                  filter_class = record_class))

    def parse_proc_spec(self, proc_spec):
        """Parse a processor specification."""
        targets = []
        # Handle some special cases for sending to all processors.
        if proc_spec.lower() == "all" or proc_spec == "-1":
            return -1
        for group in proc_spec.split(","):
            tup = group.split("-")
            try:
                if len(tup) == 1:
                    targets.append((int(tup[0]), int(tup[0])))
                else:
                    targets.append((int(tup[0]), int(tup[1])))
            except ValueError:
                print "Bad processor specification."
                return
        return Interval(intervals = targets)

    def do_proc(self, cmd, targets = None):
        """Handle the "proc" command to send commands to a subset of remote nodes based on MPI rank."""
        if targets:
            print "Recursive proc is not recursive."
            return
        proc_spec = None
        for i, char in enumerate(cmd):
            if char == " ":
                proc_spec = cmd[0:i]
                line = cmd[i + 1:].strip()
                break
        if not proc_spec:
            print "Bad processor specification."
            return

        targets = self.parse_proc_spec(proc_spec)
        cmd, args, options = self.resolve_gdbmi_command(line, err = False)
        if cmd:
            self.queue_msg(GDBMessage(CMD_MSG, targets, cmd = cmd, args = args, options = options))
        else:
            split = line.split()
            cmd = split[0]
            rest = " ".join(split[1:])
            if hasattr(self, "do_" + cmd):
                func = getattr(self, "do_" + cmd)
                func(rest, targets = targets)

    def do_block(self, cmd, targets = None):
        """Block all output from a subset of nodes."""
        to_block = self.parse_proc_spec(cmd)
        if not to_block:
            return
        # This is quite inefficient and will not scale.
        for target in to_block.members():
            if target not in self.blocks and target in self.mpiranks:
                self.blocks.append(target)

    def do_unblock(self, cmd, targets = None):
        """Unblock output from a subset of nodes."""
        to_unblock = self.parse_proc_spec(cmd)
        if not to_unblock:
            return
        keys = []
        for k, v in enumerate(self.blocks):
            if v in to_unblock:
                keys.append(k)
        for k in keys:
            del self.blocks[k]

    def do_varprint(self, cmd, targets = None):
        """Run the varprint command."""
        if not targets:
            targets = self.all_ranks
        cmd_split = cmd.split(" ")
        var = cmd
        # Strip quotes, if present.
        if var[0] == '"' and var[-1] == '"':
            var = var[1:-1]
        self.queue_msg(GDBMessage(VARPRINT_MSG, targets, name = var))

    def do_varassign(self, cmd, targets = None):
        """Run the varassign command."""
        if not targets:
            targets = self.all_ranks
        split = cmd.split("=")
        if len(split) != 2:
            print "varassign format is: var = val"
            return
        var = split[0].strip()
        if var[0] == '"' and var[-1] == '"':
            var = var[1:-1]
        val = split[1].strip()
        for rank in targets.members():
            full_name = self.varobjs[rank].get_full_name(var)
            if not full_name:
                print "Variable not found on rank {0}.".format(rank)
                continue
            self.queue_msg(GDBMessage(CMD_MSG, rank, cmd = "var_assign",
                                      args = ('"' + full_name + '"', '"' + val + '"'), options = {}))

    def do_help(self, cmd, targets = None):
        """Run the help command."""
        if not targets:
            # Because this makes the most sense, unless told otherwise, we run this on one processor.
            targets = 0
        self.queue_msg(GDBMessage(CMD_MSG, targets, cmd = "interpreter_exec",
                                  args = ("console", '"help ' + cmd + '"'), options = {}))

    def do_kill(self, cmd, targets = None):
        """Kill all targets being debugged."""
        # This always sends to all targets, for now.
        print "Sending SIGTERM to all inferiors. (May need to step them for them to die.)"
        self.queue_msg(GDBMessage(KILL_MSG, self.all_ranks))

    def queue_msg(self, msg):
        """Queue a message for sending to back-end daemons."""
        with self.msg_queue_lock:
            self.msg_queue.append(msg)
    
    def queue_msg_with_token(self, msg):
        """Queue a message for sending to back-end daemons with a unique token."""
        token = self.current_token
        self.current_token += 1
        msg.token = token
        self.queue_msg(msg)
        return token

    def dispatch_gdbmi_command(self, cmd, args, options):
        """Send a GDB command."""
        return self.queue_msg_with_token(GDBMessage(CMD_MSG, self.all_ranks, cmd = cmd, args = args,
                                                    options = options))

    def check_gdbmi_command(self, cmd):
        """Check whether a GDB command is valid."""
        try:
            return cmd in self.gdb_cmds
        except AttributeError:
            print "Tried to check a command before initialization completed."
            return False

    def send_msg(self, msg):
        """Send a message to back-end daemons."""
        stream = None
        if msg.rank == self.all_ranks:
            stream = self.broadcast_stream
        else:
            rank_list = []
            for rank in self.msg_rank_to_list(msg.rank):
                if rank not in self.mpirank_to_mrnrank:
                    print "Bad rank {0}".format(rank)
                    return
                rank_list.append(self.mpirank_to_mrnrank[rank])
            rank_list = list(set(rank_list))
            comm = self.mrnet.new_Communicator(rank_list)
            stream = self.mrnet.new_Stream(comm, 0, 0, 0)
        if stream:
            self.mrnet_stream_send_msg(stream, msg)
        else:
            print "No stream to send."

    def handle_msg(self, msg):
        """Handle a received message."""
        if msg.msg_type in self.msg_handlers:
            self.msg_handlers[msg.msg_type](msg)
        else:
            print "Got a message {0} with no handler.".format(msg.msg_type)

    def remote_body(self):
        """The main remote body thread.

        This initializes the remote infrastructure, receives and processes data, and sends data from
        the message queue.

        """
        # Must do the init inside of this thread, or else LaunchMON steals stdin.
        self.remote_init()
        print "GDB deployed to {0} hosts and {1} processors.".format(self.network_size,
                                                                     self.proctab_size)
        recvd = False
        while not self.quit:
            # Receive data, if any.
            msg, stream = self.mrnet_recv(blocking = False)
            if msg is not None:
                # Received data.
                self.handle_msg(msg)
                recvd = True
            else:
                recvd = False

            # Send data, if any.
            with self.msg_queue_lock:
                while len(self.msg_queue):
                    self.send_msg(self.msg_queue.popleft())

            # Keep from beating up the CPU too much.
            if not recvd:
                time.sleep(self.sleep_time)
        self.shutdown()
        thread.interrupt_main()
        #print "Use C-d to exit the front-end."

    def local_body(self):
        """The local command input loop."""
        try:
            self.cmdloop()
        except KeyboardInterrupt:
            print "Terminating."
            sys.exit(0)

    def run(self):
        """Start the remote thread and run the local command input loop."""
        self.parse_args()
        self.remote_thread = threading.Thread(target = self.remote_body)
        self.remote_thread.daemon = True
        self.remote_thread.start()
        self.local_body()

def run():
    """Simple function to run the front-end."""
    gdbfe = GDBFE()
    gdbfe.run()

if __name__ == "__main__":
    run()
