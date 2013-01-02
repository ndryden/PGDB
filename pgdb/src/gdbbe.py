"""The back-end daemon invoked by LaunchMON.

This handles initializing the back-end side of the LaunchMON and MRNet communication systems,
deploying GDB, and sending commands and data back and forth.

"""

from conf import gdbconf
from gdb_shared import *
from lmon.lmonbe import *
from mi.gdbmi import *
from mi.gdbmi_identifier import GDBMIRecordIdentifier
from mi.varobj import VariableObject, VariableObjectManager
import signal, os

class GDBBE:
    """The back-end GDB daemon process."""

    def init_lmon(self):
        """Initialize LaunchMON communication and collect our process table."""
        self.lmonbe = LMON_be()
        self.lmonbe.init(len(sys.argv), sys.argv)
        self.lmonbe.regPackForBeToFe(lmon.pack)
        self.lmonbe.regUnpackForFeToBe(lmon.unpack)
        self.lmonbe.handshake(None)
        self.lmonbe.ready(None)
        self.lmon_rank = self.lmonbe.getMyRank()
        self.lmon_size = self.lmonbe.getSize()
        self.lmon_master = self.lmonbe.amIMaster()
        self.proctab_size = self.lmonbe.getMyProctabSize()
        self.proctab, unused = self.lmonbe.getMyProctab(self.proctab_size)

    def init_mrnet(self):
        """Initialize MRNet by receiving the topology information and connecting to the comm nodes."""
        if self.lmon_master:
            # Master receives topology information from front-end and broadcasts to the rest.
            self.topo_info = self.lmonbe.recvUsrData(gdbconf.topology_transmit_size)
            self.lmonbe.broadcast(self.topo_info, gdbconf.topology_transmit_size)
        else:
            # Others receive the master's broadcast.
            self.topo_info = self.lmonbe.broadcast(None, gdbconf.topology_transmit_size)

        for node_info in self.topo_info.values():
            if node_info.parent == -1:
                self.mrnet_fe_rank = node_info.mrnrank
                break
        argv = self.get_mrnet_argv()
        self.mrnet = MRN.Network.CreateNetworkBE(6, argv)
        self.packet_stash = []

    def get_mrnet_argv(self):
        """Construct the argument list for MRNet's CreateNetworkBE."""
        # Find our information in the topology.
        max_rank = max(self.topo_info.keys()) + 1
        myhost = socket.getfqdn()
        for rank, node_info in self.topo_info.items():
            # This assumes a bit about the form of the domain names.
            if node_info.host == myhost:
                return [sys.argv[0], # Program name.
                        str(node_info.host), # Parent host.
                        str(node_info.port), # Parent port.
                        str(node_info.mrnrank), # Parent rank.
                        myhost, # My host.
                        str(max_rank + rank)] # My rank.
        raise ValueError("Could not find my ({0}) topology information!".format(myhost))

    def mrnet_stream_send(self, stream, msg_type, rank, **kwargs):
        """Construct, serialize, and send a GDBMessage on a given MRNet stream."""
        msg = cPickle.dumps(GDBMessage(msg_type, rank, **kwargs), 0)
        split_len = int(gdbconf.multi_len / 2)
        if len(msg) > gdbconf.multi_len:
            # We use multi-messages at this point.
            payloads = [msg[i:i + split_len] for i in range(0, len(msg), split_len)]
            # Send the initial MULTI_MSG.
            self.mrnet_stream_send(stream, MULTI_MSG, rank, num = len(payloads))
            # Send the payloads.            
            for payload in payloads:
                self.mrnet_stream_send(stream, MULTI_PAYLOAD_MSG, rank, payload = payload)
        else:
            if stream.send(MSG_TAG, "%s", msg) == -1:
                sys.exit(1)

    def mrnet_recv(self, blocking = True):
        """Receive data on MRNet and unserialize it."""
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

    def wait_for_hello(self):
        """Wait until we receive a HELLO message on MRNet."""
        msg, stream = self.mrnet_recv()
        if msg.msg_type != HELLO_MSG:
            print "Didn't get hello."
            sys.exit(1)
        self.mrnet_fe_stream = stream

    def init_gdb(self):
        """Initialize GDB-related things, including launching the GDB process."""
        # Indexed by MPI rank.
        self.gdb = {}
        self.varobjs = {}
        self.varprint_id = 0
        self.varprint_stacks = {}

        # Default handler to ignore things.
        def handler(record):
            return True

        for proc in self.proctab:
            self.gdb[proc.mpirank] = GDBMachineInterface(gdb_args = ["-x", gdbconf.gdb_init_path],
                                                         default_handler = handler)
            # Attach to the process.
            if not self.gdb_run_cmd(proc.mpirank, "attach", (proc.pd.pid, ), {}):
                raise RuntimeError("Could not attach to process!")
            # Enable pretty-printing by default.
            # TODO: Make this optional.
            if not self.gdb_run_cmd(proc.mpirank, "enable_pretty_printing", (), {}):
                raise RuntimeError("Could not enable pretty printing!")
            self.varobjs[proc.mpirank] = VariableObjectManager()

        # Master sends commands list back to front-end.
        if self.lmon_master:
            self.lmonbe.sendUsrData(self.gdb[self.proctab[0].mpirank].commands.keys())

    def quit_all(self):
        """Terminate all targets being debugged.

        This sends SIGTERM."""
        for proc in self.proctab:
            os.kill(proc.pd.pid, signal.SIGTERM)

    def msg_rank_to_list(self, msg_rank):
        """Convert a "rank" to a list of ranks.

        Ranks can be represented in a number of ways; -1 stands for all ranks we have.
        A single integer refers to that rank.
        There can be a list of ranks, which is just returned as is.
        There can be a list of tuples indicating ranges of ranks, inclusively, which are expanded
        into a list of ranks.

        """
        if isinstance(msg_rank, int):
            return [msg_rank]
        return msg_rank.members()
        if isinstance(msg_rank, int):
            if msg_rank == -1:
                return self.gdb.keys()
            else:
                return [msg_rank]
        elif isinstance(msg_rank, list):
            if isinstance(msg_rank[0], tuple):
                ranks = []
                for rank_tup in msg_rank:
                    ranks += range(rank_tup[0], rank_tup[1] + 1)
                return ranks
            else:
                return msg_rank
        return False

    def gdb_run_cmd(self, rank, cmd, args, options, token = None, handler = None):
        """Run a GDB command on a set of GDB processes."""
        ranks = self.msg_rank_to_list(rank)
        for rank2 in ranks:
            if rank2 in self.gdb:
                func = getattr(self.gdb[rank2], cmd)
                func(*args, options = options, token = token, handler = handler)
        return True

    def init_handlers(self):
        """Initialize message handlers used on data we receive over MRNet."""
        self.msg_handlers = {
            DIE_MSG: self.die_handler,
            CMD_MSG: self.cmd_handler,
            FILTER_MSG: self.filter_handler,
            UNFILTER_MSG: self.unfilter_handler,
            VARPRINT_MSG: self.varprint_handler,
            KILL_MSG: self.kill_handler
            }

    def init_filters(self):
        """Initialize default filters."""
        an_lower = ASYNC_NOTIFY.lower()
        self.filters = [
            (an_lower, "shlibs-updated"),
            (an_lower, "shlibs-added"),
            (an_lower, "shlibs-removed"),
            (an_lower, "library-loaded"),
            (an_lower, "thread-created"),
            (an_lower, "thread-group-added"),
            (an_lower, "thread-group-started"),
            (RESULT.lower(), "exit")
            ]

    def __init__(self):
        """Initialize LaunchMON, MRNet, GDB, and other things."""
        self.is_shutdown = False
        self.quit = False
        self.init_lmon()
        self.init_mrnet()
        self.wait_for_hello()
        self.init_gdb()
        self.init_handlers()
        self.init_filters()

    def shutdown(self):
        """Cleanly shut things down if we have not already done so."""
        if not self.is_shutdown:
            self.lmonbe.finalize()
            self.mrnet.waitfor_ShutDown()
            try:
                del self.mrnet
            except AttributeError: pass
            self.is_shutdown = True
        
    def __del__(self):
        """Invoke shutdown()."""
        self.shutdown()

    def die_handler(self, msg):
        """Handle a die message by exiting."""
        sys.exit("Told to die.")

    def cmd_handler(self, msg):
        """Handle a CMD message by running the command.

        The message needs the following fields:
        cmd - the command to run.
        args - the positional arguments to the command.
        options - the options to the command.
        rank - the ranks to run the command on.
        token - optional, the token to use for the command.

        """
        if msg.cmd == "quit":
            # Special case for quit.
            self.quit = True
        token = None
        if hasattr(msg, "token"):
            token = msg.token
        if not self.gdb_run_cmd(msg.rank, msg.cmd, msg.args, msg.options, token = token):
            # TODO: Send die message.
            print "Managed to get a bad command '{0}'.".format(msg.cmd)

    def kill_handler(self, msg):
        """Handle a kill message, killing all processes."""
        self.quit_all()
            
    def filter_handler(self, msg):
        """Handle a filter message by adding the filter."""
        self.filters.append((msg.filter_type, msg.filter_class))

    def unfilter_handler(self, msg):
        """Handle an unfilter message by removing the filter."""
        try:
            self.filters.remove((msg.filter_type, msg.filter_class))
        except ValueError:
            # Ignore non-existent filter removals.
            pass

    def is_filterable(self, record):
        """Check whether a given record can be filtered."""
        record_type = record.record_type.lower()
        if record_type == RESULT.lower():
            record_class = record.result_class.lower()
        elif record_type in map(lambda x: x.lower(), [ASYNC_EXEC, ASYNC_STATUS, ASYNC_NOTIFY]):
            record_class = record.output_class.lower()
        else:
            record_class = None
        if (record_type, record_class) in self.filters:
            return True
        return False

    def varprint_handler(self, msg):
        """Handle the varprint message and begin the varprint sequence.

        The message has the fields
        rank - the ranks to query.
        name - the name of the variable.

        To varprint, we first run varprint_update, to update our cached varobjs.
        Then we run another handler that checks if we have the variable object already.
        If not, we do a depth-first search and eventually return the result.

        """
        for rank in msg.rank.intersect_list(self.gdb.keys()):
            self.varprint_update(msg.name, rank)

    def varprint_handler2(self, name, rank):
        """Follow-up varprint handler after udating, starts the DFS."""
        # Check if we already have the variable object.
        varobj = self.varobjs[rank].get_var_obj(name)
        if varobj:
            if not varobj.listed or varobj.more_children:
                # If we explicitly list this variable, print all of its children.
                self.varprint_start_no_create(rank, varobj, name,
                                              max_children = sys.maxsize, reset_maxes = True)
            else:
                self.mrnet_stream_send(self.mrnet_fe_stream, VARPRINT_RES_MSG,
                                       rank, err = False, varobj = varobj)
        else:
            # We do not. Start from the closest ancestor we have.
            ancestor = self.varobjs[rank].get_lowest_ancestor(name)
            if ancestor:
                # Start by listing the children of the ancestor.
                self.varprint_start_no_create(rank, ancestor, name)
            else:
                self.varprint_start(rank, name)

    def varprint_update(self, name, rank):
        """Check for updates on any of our variable objects."""
        def _update_handler(record):
            if "changelist" not in record.results:
                print "Got a bad update record."
                return True
            for change in record.results["changelist"]:
                varobj = self.varobjs[rank].get_var_obj(change["name"])
                if varobj:
                    # Potentially, a variable object could be manually created that we're not tracking.
                    if "in_scope" in change:
                        if change["in_scope"] in ["false", "invalid"]:
                            self.varobjs[rank].del_var_obj(varobj)
                            del varobj # This probably isn't necessary.
                            return False
                    if "type_changed" in change and change["type_changed"] == "true":
                        self.varobjs[rank].del_var_obj(varobj)
                        del varobj
                        return False
                    if "value" in change:
                        varobj.value = change["value"]
                    if "dynamic" in change:
                        varobj.is_dynamic = change["dynamic"]
                    if "displayhint" in change:
                        varobj.display_hint = change["displayhint"]
                    if "num_new_children" in change:
                        new_num = int(change["new_num_children"])
                        if new_num < len(varobj.children):
                            # There has been a removal, so we no longer have child information.
                            varobj.children = []
                            varobj.listed = False
                            varobj.has_more = False
                        else:
                            if "new_children" in change:
                                for child in change["new_children"]:
                                    varobj = VariableObjectManager.create_var_obj(child)
                                    if not varobj:
                                        print "Could not create child varobj!"
                                        return True
                                    if not self.varobjs[rank].add_var_obj(varobj):
                                        print "Could not add child varobj!"
                                        return True
            self.varprint_handler2(name, rank)
        self.gdb_run_cmd(rank, "var_update", ("1", "*"), {}, handler = _update_handler)

    def varprint_start(self, rank, name, max_depth = gdbconf.varprint_max_depth,
                       max_children = gdbconf.varprint_max_children, reset_maxes = False):
        """Start a varprint command sequence by creating the varobj in GDB."""
        v_id = self.varprint_id
        self.varprint_id += 1
        base_name = VariableObjectManager.get_base_name(name)
        branch_depth = max_depth + VariableObjectManager.get_name_depth(name)
        def _list_handler(record):
            return self.varprint_dfs(record, rank, v_id, name, max_depth = max_depth,
                                     max_children = max_children, reset_maxes = False,
                                     branch_depth = branch_depth, branch_name = name)
        def _create_handler(record):
            varobj = VariableObjectManager.create_var_obj(record.results)
            if not varobj:
                # Bad variable name.
                return True
            if not self.varobjs[rank].add_var_obj(varobj):
                print "Could not add varobj."
            if int(varobj.num_child) > 0 or varobj.is_dynamic:
                # Set up our stack.
                self.varprint_stacks[v_id] = [(varobj, 0)]
                self.gdb_run_cmd(rank, "var_list_children", ("1", record.results["name"]), {},
                                 handler = _list_handler)
            else:
                self.mrnet_stream_send(self.mrnet_fe_stream, VARPRINT_RES_MSG, rank, err = False,
                                       varobj = varobj)
        self.gdb_run_cmd(rank, "var_create", (base_name, "*", base_name), {},
                         handler = _create_handler)

    def varprint_start_no_create(self, rank, varobj, name, max_depth = gdbconf.varprint_max_depth,
                                 max_children = gdbconf.varprint_max_children, reset_maxes = False):
        """Start a varprint sequence where we have already created the variable object."""
        v_id = self.varprint_id
        self.varprint_id += 1
        self.varprint_stacks[v_id] = [(varobj, 0)]
        branch_depth = max_depth = VariableObjectManager.get_name_depth(name)
        def _list_handler(record):
            return self.varprint_dfs(record, rank, v_id, name, max_depth = max_depth,
                                     max_children = max_children, reset_maxes = reset_maxes,
                                     branch_depth = branch_depth, branch_name = name)
        self.gdb_run_cmd(rank, "var_list_children", ("1", '"' + varobj.name + '"'), {},
                         handler = _list_handler)
                        
    def varprint_dfs(self, record, rank, v_id, name, max_depth = gdbconf.varprint_max_depth,
                     max_children = gdbconf.varprint_max_children,
                     reset_maxes = False, branch_depth = None, branch_name = None):
        """Do the depth-first search for expanding a variable object's children."""
        cur_varobj, parent_depth = self.varprint_stacks[v_id].pop()
        cur_varobj.listed = True
        if "has_more" not in record.results:
            self.mrnet_stream_send(self.mrnet_fe_stream, VARPRINT_RES_MSG,
                                   rank, err = True, msg = "Got bad variable data.")
        elif "children" in record.results:
            if len(record.results["children"]) > max_children:
                cur_varobj.more_children = True
            for child_tup in record.results["children"][:max_children]:
                child = child_tup[1]
                varobj = VariableObjectManager.create_var_obj(child)
                if not varobj:
                    print "Could not create child varobj!"
                    return True
                if not self.varobjs[rank].add_var_obj(varobj):
                    print "Could not add child varobj!"
                    return True
                if int(varobj.num_child) > 0 or varobj.is_dynamic:
                    # Only potentially push if the varobj can have children.
                    do_listing = True
                    if parent_depth > max_depth:
                        # If the depth of the parent of this node is greater than five,
                        # we want to terminate the search of this branch, unless this
                        # node is a pseduo-child, or we want to go deeper on one branch.
                        if branch_name and VariableObjectManager.same_branch(varobj.name, branch_name):
                            if parent_depth > branch_depth and not VariableObjectManager.is_pseudochild(varobj):
                                do_listing = False
                        elif not VariableObjectManager.is_pseudochild(varobj):
                            do_listing = False
                    # Don't list null-pointers.
                    if varobj.vartype and varobj.value and varobj.vartype[-1] == "*":
                        try:
                            if int(varobj.value, 0) == 0:
                                do_listing = False
                        except ValueError: pass
                    # Do not evaluate children further when there's an excessive number.
                    if len(record.results["children"]) > 128:
                        do_listing = False
                    # Add to the stack to list if we meet the requirements.
                    if do_listing:
                        self.varprint_stacks[v_id].append((varobj, parent_depth + 1))
        if not self.varprint_stacks[v_id]:
            to_send = self.varobjs[rank].get_var_obj(name)
            if to_send:
                self.mrnet_stream_send(self.mrnet_fe_stream, VARPRINT_RES_MSG, rank, err = False,
                                       varobj = to_send)
            else:
                self.mrnet_stream_send(self.mrnet_fe_stream, VARPRINT_RES_MSG, rank, err = True,
                                       msg = "Variable does not exist.")
        else:
            to_list, depth = self.varprint_stacks[v_id][-1]
            if reset_maxes:
                def _list_handler(record):
                    return self.varprint_dfs(record, rank, v_id, name, branch_depth = branch_depth,
                                             branch_name = branch_name)
            else:
                def _list_handler(record):
                    return self.varprint_dfs(record, rank, v_id, name, max_depth = max_depth,
                                             max_children = max_children, reset_maxes = reset_maxes,
                                             branch_depth = branch_depth, branch_name = branch_name)
            self.gdb_run_cmd(rank, "var_list_children", ("1", '"' + to_list.name + '"'),
                             {}, handler = _list_handler)

    def main(self):
        """Main send/receive loop.

        This receives data on MRNet (non-blocking), processes the messages, and then sends any
        data that was read from GDB. This then sleeps for a short while to avoid heavy CPU use.

        """
        while True:
            if self.quit:
                break
            # TODO: Check for memory leaks relating to these.
            msg, stream = self.mrnet_recv(blocking = False)
            if msg is not None:
                # Received data.
                if msg.msg_type in self.msg_handlers:
                    self.msg_handlers[msg.msg_type](msg)
                else:
                    print "Got a message {0} with no handler.".format(msg.msg_type)

            for rank, gdb in self.gdb.items():
                for record in gdb.read():
                    if not self.is_filterable(record):
                        self.mrnet_stream_send(self.mrnet_fe_stream, OUT_MSG, rank, record = record)

            # Sleep a bit to reduce banging on the CPU.
            time.sleep(0.01)
        # Wait for GDB to exit.
        while True:
            exited = True
            for gdb in self.gdb.values():
                exited = exited and (not gdb.is_running())
            if exited:
                break

def run():
    """Simple function to run the backend."""
    gdbbe = GDBBE()
    gdbbe.main()

if __name__ == "__main__":
    run()
