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
from mi.gdbmiarec import GDBMIAggregatedRecord, combine_aggregation_lists
from interval import Interval
from varprint import VariablePrinter
import signal, os

class GDBBE:
    """The back-end GDB daemon process."""

    def init_gdb(self):
        """Initialize GDB-related things, including launching the GDB process."""
        # Indexed by MPI rank.
        self.gdb = {}
        self.varobjs = {}

        enable_pprint_cmd = Command("enable-pretty-printing")
        enable_target_async_cmd = Command("gdb-set", args = ["target-async", "on"])
        disable_pagination_cmd = Command("gdb-set", args = ["pagination", "off"])
        enable_non_stop_cmd = Command("gdb-set", args = ["non-stop", "on"])
        for proc in self.comm.get_proctab():
            self.gdb[proc.mpirank] = GDBMachineInterface(gdb_args = ["-x", gdbconf.gdb_init_path])
            # Enable pretty-printing by default.
            # TODO: Make this optional.
            if not self.run_gdb_command(enable_pprint_cmd, Interval(lis = [proc.mpirank])):
                raise RuntimeError("Could not enable pretty printing on rank {0}!".format(proc.mpirank))
            if not self.run_gdb_command(enable_target_async_cmd, Interval(lis = [proc.mpirank])):
                raise RuntimeError("Could not enable target-async on rank {0}!".format(proc.mpirank))
            if not self.run_gdb_command(disable_pagination_cmd, Interval(lis = [proc.mpirank])):
                raise RuntimeError("Could not disable pagination on rank {0}!".format(proc.mpirank))
            if not self.run_gdb_command(enable_non_stop_cmd, Interval(lis = [proc.mpirank])):
                raise RuntimeError("Could not enable non-stop on rank {0}!".format(proc.mpirank))
            # Attach to the process.
            if not self.run_gdb_command(Command("target-attach", args = [proc.pd.pid]), Interval(lis = [proc.mpirank])):
                raise RuntimeError("Could not attach to rank {0}!".format(proc.mpirank))
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

        Returns a dictionary, indexed by ranks, of the tokens used.

        """
        cmd_str = command.generate_mi_command()
        if isinstance(ranks, int):
            # Special case for a single int.
            # Toss it in a list; don't need a full Interval.
            ranks = [ranks]
        tokens = {}
        for rank in ranks:
            if rank in self.gdb:
                tokens[rank] = self.gdb[rank].send(cmd_str, token)
        return tokens

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
        self.token_handlers = {}
        self.comm = CommunicatorBE()
        self.comm.init_lmon(sys.argv)
        self.comm.init_mrnet()
        self.init_gdb()
        self.init_handlers()
        self.init_filters()
        self.variable_printer = VariablePrinter(self)

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

    def add_token_handler(self, token, handler):
        """Add a handler for the given token.

        token is the token to trigger on.
        handler is a callback function that accepts the record.

        There can be at most one handler for a given token.

        """
        self.token_handlers[token] = handler

    def del_token_handler(self, token):
        """Remove a handler for the given token.

        token is the token handler to remove.

        """
        if token in self.token_handlers:
            del self.token_handlers[token]
            return True
        return False

    def _call_token_handler(self, record):
        """Given a record, call the associated token handler if any."""
        if record.token in self.token_handlers:
            self.token_handlers[record.token](record)

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
        if msg.command.command == "gdb-exit":
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

    def varprint_handler(self, msg):
        """Handle the varprint message and begin sequence. See VariablePrinter."""
        self.variable_printer.varprint_handler(msg)

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

            arec_list = []
            for rank, gdb in self.gdb.items():
                for record in gdb.read():
                    if not self.is_filterable(record):
                        self._call_token_handler(record)
                        arec_list.append([GDBMIAggregatedRecord(record, rank)])
            if arec_list:
                combined_list = arec_list.pop(0)
                for arec in arec_list:
                    combined_list = combine_aggregation_lists(combined_list, arec)
                self.comm.send(GDBMessage(OUT_MSG, record = combined_list), self.comm.frontend)

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
