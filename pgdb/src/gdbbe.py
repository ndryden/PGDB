"""The back-end daemon invoked by LaunchMON.

This handles initializing the back-end side of the LaunchMON and MRNet communication systems,
deploying GDB, and sending commands and data back and forth.

"""

from conf import gdbconf
from comm import *
from gdb_shared import *
from lmon.lmonbe import *
from mi.gdbmi import *
from mi.gdbmi_identifier import GDBMIRecordIdentifier
from mi.varobj import VariableObject, VariableObjectManager
from mi.commands import Command
from interval import Interval
import signal, os

class GDBBE:
    """The back-end GDB daemon process."""

    def init_gdb(self):
        """Initialize GDB-related things, including launching the GDB process."""
        # Indexed by MPI rank.
        self.gdb = {}
        self.varobjs = {}
        self.varprint_id = 0
        self.varprint_stacks = {}

        enable_pprint_cmd = Command("enable-pretty-printing")
        for proc in self.comm.get_proctab():
            self.gdb[proc.mpirank] = GDBMachineInterface(gdb_args = ["-x", gdbconf.gdb_init_path])
            # Attach to the process.
            if not self.run_gdb_command(Command("target-attach", args = [proc.pd.pid]), Interval(lis = [proc.mpirank])):
                raise RuntimeError("Could not attach to rank {0}!".format(proc.mpirank))
            # Enable pretty-printing by default.
            # TODO: Make this optional.
            if not self.run_gdb_command(enable_pprint_cmd, Interval(lis = [proc.mpirank])):
                raise RuntimeError("Could not enable pretty printing on rank {0}!".format(proc.mpirank))
            self.varobjs[proc.mpirank] = VariableObjectManager()

    def quit_all(self):
        """Terminate all targets being debugged.

        This sends SIGTERM."""
        for proc in self.proctab:
            os.kill(proc.pd.pid, signal.SIGTERM)

    def run_gdb_command(self, command, ranks, token = None):
        """Run a GDB command.

        command is a Command object representing the command.
        ranks is an Interval of the ranks to run the command on.
        token is the optional token to use.

        """
        cmd_str = command.generate_mi_command()
        for rank in ranks:
            if rank in self.gdb:
                self.gdb[rank].send(cmd_str, token)
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
        self.comm = CommunicatorBE()
        self.comm.init_lmon(sys.argv)
        self.comm.init_mrnet()
        self.init_gdb()
        self.init_handlers()
        self.init_filters()

    def shutdown(self):
        """Cleanly shut things down if we have not already done so."""
        if not self.comm.is_shutdown():
            self.comm.shutdown()

    def __del__(self):
        """Invoke shutdown()."""
        # Exception guard if we have an error before comm init.
        try:
            self.shutdown()
        except AttributeError: pass

    def die_handler(self, msg):
        """Handle a die message by exiting."""
        sys.exit("Told to die.")

    def cmd_handler(self, msg):
        """Handle a CMD message by running the command.

        The message contains the following fields:
        command - A Command object to run.
        ranks - An optional interval of ranks on which to run.
        token - An optional token to use.

        """
        if msg.command.command == "quit":
            # Special case for quit.
            self.quit = True
        token = None
        if hasattr(msg, "token"):
            token = msg.token
        ranks = self.comm.get_mpiranks()
        if hasattr(msg, "ranks"):
            ranks = msg.ranks
        if not self.run_gdb_command(msg.command, ranks, token = token):
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
            msg = self.comm.recv(blocking = False)
            if msg is not None:
                # Received data.
                if msg.msg_type in self.msg_handlers:
                    self.msg_handlers[msg.msg_type](msg)
                else:
                    print "Got a message {0} with no handler.".format(msg.msg_type)

            for rank, gdb in self.gdb.items():
                for record in gdb.read():
                    if not self.is_filterable(record):
                        self.comm.send(GDBMessage(OUT_MSG, record = record, rank = rank), self.comm.frontend)

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
