"""The back-end daemon invoked by LaunchMON.

This handles initializing the back-end side of the LaunchMON and MRNet communication systems,
deploying GDB, and sending commands and data back and forth.

"""

from conf import gdbconf
from comm import *
from gdb_shared import *
from lmon.lmonbe import *
from mi.gdbmi import *
from mi.varobj import VariableObject, VariableObjectManager
from mi.commands import Command
from mi.gdbmiarec import GDBMIAggregatedRecord, combine_records
from interval import Interval
from varprint import VariablePrinter
import signal, os

class GDBBE:
    """The back-end GDB daemon process."""

    def init_gdb(self):
        """Initialize GDB-related things, including launching the GDB process."""
        # Indexed by MPI rank.
        self.varobjs = {}
        # Maps tokens to MPI rank.
        self.token_rank_map = {}

        enable_pprint_cmd = Command("enable-pretty-printing")
        enable_target_async_cmd = Command("gdb-set", args = ["target-async", "on"])
        disable_pagination_cmd = Command("gdb-set", args = ["pagination", "off"])
        enable_non_stop_cmd = Command("gdb-set", args = ["non-stop", "on"])
        add_inferior_cmd = Command("add-inferior")
        self.gdb = GDBMachineInterface(gdb = gdbconf.gdb_path,
                                       gdb_args = ["-x", gdbconf.gdb_init_path])
        procs = self.comm.get_proctab()
        # Set up GDB.
        if not self.run_gdb_command(enable_pprint_cmd):
            raise RuntimeError("Could not enable pretty printing!")
        if not self.run_gdb_command(enable_target_async_cmd):
            raise RuntimeError("Could not enable target-async!")
        if not self.run_gdb_command(disable_pagination_cmd):
            raise RuntimeError("Could not disable pagination!")
        if not self.run_gdb_command(enable_non_stop_cmd):
            raise RuntimeError("Could not enable non-stop!")

        # Create inferiors and set up MPI rank/inferior map.
        # First inferior is created by default.
        self.rank_inferior_map = {procs[0].mpirank: 'i1'}
        i = 2
        for proc in procs[1:]:
            # Hackish: Assume that the inferiors follow the iN naming scheme.
            self.rank_inferior_map[proc.mpirank] = 'i' + str(i)
            i += 1
            if not self.run_gdb_command(add_inferior_cmd):
                raise RuntimeError('Cound not add inferior i{0}!'.format(i - 1))

        # Attach processes.
        for proc in procs:
            if not self.run_gdb_command(Command("target-attach",
                                                args = [proc.pd.pid]),
                                        proc.mpirank):
                raise RuntimeError("Could not attach to rank {0}!".format(proc.mpirank))
            self.varobjs[proc.mpirank] = VariableObjectManager()

    def quit_all(self):
        """Terminate all targets being debugged.

        This sends SIGTERM."""
        for proc in self.proctab:
            os.kill(proc.pd.pid, signal.SIGTERM)

    def run_gdb_command(self, command, ranks = None, token = None):
        """Run a GDB command.

        command is a Command object representing the command.
        ranks is an Interval of the ranks to run the command on.
        If ranks is None, run on the current GDB inferior.
        token is the optional token to use.

        Returns a dictionary, indexed by ranks, of the tokens used.
        If running on the current inferior, the "rank" is -1.

        """
        if isinstance(ranks, int):
            # Special case for a single int.
            # Toss it in a list; don't need a full Interval.
            ranks = [ranks]
        tokens = {}
        if not ranks:
            # Send to the current inferior.
            tokens[-1] = self.gdb.send(command.generate_mi_command(), token)
        else:
            for rank in ranks:
                if rank in self.rank_inferior_map:
                    # Most recent option with same name takes precedence.
                    command.add_opt('--thread-group', self.rank_inferior_map[rank])
                    ret_token = self.gdb.send(command.generate_mi_command(),
                                              token)
                    tokens[rank] = ret_token
                    self.token_rank_map[ret_token] = rank
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
        self.filters = set()
        #an_lower = ASYNC_NOTIFY.lower()
        #self.filters = [
        #    (an_lower, "shlibs-updated"),
        #    (an_lower, "shlibs-added"),
        #    (an_lower, "shlibs-removed"),
        #    (an_lower, "library-loaded"),
        #    (an_lower, "thread-created"),
        #    (an_lower, "thread-group-added"),
        #    (an_lower, "thread-group-started"),
        #    (RESULT.lower(), "exit")
        #    ]

    def __init__(self):
        """Initialize LaunchMON, MRNet, GDB, and other things."""
        self.is_shutdown = False
        self.quit = False
        self.token_handlers = {}
        self.comm = CommunicatorBE()
        if not self.comm.init_lmon(sys.argv):
            sys.exit(1)
        if not self.comm.init_mrnet():
            # TODO: This should cleanly terminate LaunchMON, but does not.
            sys.exit(1)
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
        self.filters.update(msg.filter_types)

    def unfilter_handler(self, msg):
        """Handle an unfilter message by removing the filter."""
        self.filters.difference_update(msg.filter_types)

    def varprint_handler(self, msg):
        """Handle the varprint message and begin sequence. See VariablePrinter."""
        self.variable_printer.varprint_handler(msg)

    def is_filterable(self, record):
        """Check whether a given record can be filtered."""
        record_set = record.record_subtypes.union([record.record_type])
        if record_set.intersection(self.filters):
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

            records = []
            ranks = []
            for record in self.gdb.read():
                if not self.is_filterable(record):
                    records.append(record)
                    if record.token and record.token in self.token_rank_map:
                        ranks.append(self.token_rank_map[record.token])
                    else:
                        ranks.append(-1)
            if records:
                arecs = combine_records(records, ranks)
                self.comm.send(GDBMessage(OUT_MSG, record = arecs), self.comm.frontend)

            # Sleep a bit to reduce banging on the CPU.
            time.sleep(0.01)
        # Wait for GDB to exit.
        exited = False
        while not exited:
            exited = not self.gdb.is_running()
        # Shut everything else down.
        self.shutdown()

def run():
    """Simple function to run the backend."""
    gdbbe = GDBBE()
    gdbbe.main()

if __name__ == "__main__":
    run()
