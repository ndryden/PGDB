"""The front-end interface to PGDB.

This handles user input, deploying the network and remote debuggers, and everything else related to
this.

"""

import os, os.path, threading, signal
from collections import deque
from conf import gdbconf
from gdb_shared import *
from comm import *
from mi.gdbmicmd import GDBMICmd
from mi.gdbmi_recordhandler import GDBMIRecordHandler
from mi.varobj import VariableObject, VariableObjectManager
from mi.commands import Command
from mi.gdbmiarec import GDBMIAggregatedRecord, combine_aggregated_records
from mi.gdbmipprinter import GDBMIPrettyPrinter
from interval import Interval
from sbd import SBDFE

class GDBFE (GDBMICmd):
    """The front-end to PGDB."""

    def init_handlers(self):
        """Initialize the message handlers and the record handler."""
        # Set up message handlers.
        self.msg_handlers = {
            DIE_MSG: self.die_handler,
            QUIT_MSG: self.quit_handler,
            OUT_MSG: self.out_handler,
            VARPRINT_RES_MSG: self.varprint_res_handler,
            LOAD_FILE: self.load_file_handler
            }
        # Now record handlers.
        self.record_handler = GDBMIRecordHandler()

    def remote_init(self):
        """Initialize things related to the remote communication and back-end daemons."""
        self.comm = CommunicatorFE(True) # Initialize with locking.
        # One of {pid} and {launcher, launcher_args} will not be none, based
        # upon the command line input parsing.
        ret = self.comm.init_lmon(self.lmon_attach, pid = self.lmon_pid,
                                  launcher = self.lmon_launcher,
                                  launcher_args = self.lmon_launcher_argv,
                                  host = self.lmon_host)
        if not ret:
            # Terminate. Note at this point main is still waiting on the remote_up event,
            # so we have to set it.
            self.remote_up.set()
            self.interrupt_main()
            return False
        ret = self.comm.init_mrnet(local = self.local_launch)
        if not ret:
            # Terminate. See prior comment about remote_up.
            self.remote_up.set()
            self.interrupt_main()
            return False
        self.varobjs = {}
        for rank in self.comm.get_mpiranks():
            self.varobjs[rank] = VariableObjectManager()
        self.init_handlers()
        self.pprinter = GDBMIPrettyPrinter()
        self.sleep_time = 0.1
        self.blocks = []
        try:
            self.blocks += gdbconf.default_blocks
        except AttributeError: pass
        # Initialize the SBD system if needed.
        if gdbconf.use_sbd:
            self.sbd = SBDFE(self.comm)
        else:
            self.sbd = None
        return True

    def __init__(self):
        """Initialize some local things; the remote initialization must be done seperately."""
        GDBMICmd.__init__(self)
        self.quit = False
        self.is_shutdown = False
        # Need to disable readline.
        self.completekey = None
        # Event triggered when remote_init completes in the remote thread..
        self.remote_up = threading.Event()
        # Temporary list for building up aggregated records from OUT messages.
        self.arec_list = []
        # Output history for expanding commands.
        self.output_history = []
        # Get our PID for signals.
        self.my_pid = os.getpid()

    def interrupt_main(self):
        """Interrupt the main thread.

        This works because in Python, the main thread is the one that processes signals.
        If using Python 3, this could be replaced with signal.pthread_kill (but this will
        work in Python 3).
        """
        os.kill(self.my_pid, signal.SIGINT)

    def parse_args(self):
        """Parse the command-line arguments and set appropriate variables."""
        # Optparse unfortunately doesn't work here.
        self.lmon_attach = None
        self.lmon_pid = None
        self.lmon_launcher = None
        self.lmon_launcher_argv = None
        self.lmon_host = None
        self.local_launch = False
        for i in range(1, len(sys.argv)):
            if sys.argv[i] == "-p" or sys.argv[i] == "--pid":
                self.lmon_attach = True
                if len(sys.argv) == i + 1:
                    print "Must provide a PID with {0}.".format(sys.argv[i])
                    sys.exit(0)
                try:
                    self.lmon_pid = int(sys.argv[i + 1])
                except ValueError:
                    print "Must provide a valid PID."
                    sys.exit(0)
                i += 1
            elif sys.argv[i] == "--launcher":
                if len(sys.argv) == i + 1:
                    print "Must provide a launcher with --launcher."
                    sys.exit(0)
                self.lmon_launcher = sys.argv[i + 1]
                i += 1
            elif sys.argv[i] == "--local":
                self.local_launch = True
            elif sys.argv[i] == "-h" or sys.argv[i] == "--host":
                if len(sys.argv) == i + 1:
                    print "Must provide a host with --host."
                    sys.exit(0)
                self.lmon_host = sys.argv[i + 1]
                i += 1
            elif sys.argv[i] == "-a":
                if not hasattr(self, "lmon_launcher"):
                    self.lmon_launcher = "srun"
                self.lmon_attach = False
                self.lmon_launcher_argv = sys.argv[i + 1:]
                break
            elif sys.argv[i] == "--sbd":
                # Override the configuration option.
                gdbconf.use_sbd = True
        if self.lmon_attach is None:
            print "Arguments: (one of -p/--pid and -a is required)"
            print "-p, --pid <pid>: attach to mpirun process <pid>"
            print "-a <options>: pass <options> verbatim to the resource manager for launching."
            print "--launcher <launcher>: use binary <launcher> to launch."
            print "--local: deploy for debugging just on the local node"
            print "-h/--host: the host the mpirun process is running on"
            print "--sbd: use the Scalable Binary Deployment system"
            sys.exit(0)

    def shutdown(self):
        """Shut down the network if not already shut down."""
        if not self.comm.is_shutdown():
            self.comm.shutdown()

    def __del__(self):
        """Invoke shutdown()."""
        # Need to catch a potential exception when comm does not exist.
        # This occurs if there is an error before comm init.
        try:
            self.shutdown()
        except AttributeError: pass

    def die_handler(self, msg):
        """Handle a die message. Presently does nothing."""
        pass

    def quit_handler(self, msg):
        """Handle a quit message. Presently does nothing."""
        pass

    def out_handler(self, msg):
        """Handle an out message by adding the arec to the temporary list."""
        if self.arec_list:
            self.arec_list = combine_aggregated_records(self.arec_list + msg.record)
        else:
            self.arec_list = msg.record

    def process_out_messages(self):
        """Go through the temporary arec_list and pretty-print records."""
        for arec in self.arec_list:
            # Add the record to the history.
            self.output_history = [arec] + self.output_history
            if len(self.output_history) > gdbconf.history_length:
                # Remove the last (oldest) element.
                self.output_history.pop()
            record_classes = arec.get_record_classes()
            class_key = max(record_classes,
                            key = lambda x: len(record_classes[x]))
            # Only print the lowest-rank entry in the class.
            ranks = record_classes[class_key]
            record = arec.get_record(ranks.get_smallest())
            # Note that this may not work if things don't support lists of ranks.
            if all(self.record_handler.handle(record, rank = ranks)):
                self.pprinter.pretty_print(record, ranks)
                if len(record_classes) > 1:
                    print "Some results from {0} omitted; use expand to view.".format(arec.get_ranks())
        self.arec_list = []

    def varprint_res_handler(self, msg):
        """Handle a varprint result message by pretty-printing the variable objects."""
        if msg.err:
            print "[{0}] {1}".format(msg.rank, msg.msg)
        elif msg.varobj:
            self.varobjs[msg.rank].add_var_obj(msg.varobj)
            print self.pprinter.varobj_pretty_print(msg.varobj, tag = msg.rank)[:-1]
        else:
            print "[{0}] Received a bad varobj!".format(msg.rank)

    def load_file_handler(self, msg):
        """Handle a load file message by loading the file and broadcasting it."""
        if self.sbd:
            self.sbd.load_file(msg.filename)
        else:
            print "Received SBD LOAD_FILE request when SBD is not enabled."

    def parse_filter_spec(self, spec):
        """Parse a filter specification into a list of record type."""
        split = spec.lower().split()
        if len(split) == 0:
            print "Bad filter specification."
            return None
        return split

    def do_filter(self, cmd, targets = None):
        """Tell the back-end daemons to filter something.

        The input is a list of record types and subtypes. A record containing
        any of these will be filtered.

        """
        record_types = set(self.parse_filter_spec(cmd))
        if not record_types:
            return
        self.comm.send(GDBMessage(FILTER_MSG, filter_types = record_types),
                       self.comm.broadcast)

    def do_unfilter(self, cmd, targets = None):
        """Tell the back-end daemons to unfilter something."""
        record_types = set(self.parse_filter_spec(cmd))
        if not record_types:
            return
        self.comm.send(GDBMessage(UNFILTER_MSG, filter_types = record_types),
                       self.comm.broadcast)

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
        return Interval(targets)

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
        if not (targets - self.comm.get_mpiranks()).empty():
            print "Out-of-range processor specification."
            return
        cmd = self.resolve_gdbmi_command(line, err = False)
        if cmd:
            self.comm.send(GDBMessage(CMD_MSG, command = cmd, ranks = targets), targets)
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
            if target not in self.blocks and target in self.comm.get_mpiranks():
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
            targets = self.comm.get_mpiranks()
        cmd_split = cmd.split(" ")
        var = cmd
        # Strip quotes, if present.
        if var[0] == '"' and var[-1] == '"':
            var = var[1:-1]
        self.comm.send(GDBMessage(VARPRINT_MSG, name = var, ranks = targets), targets)

    def do_varassign(self, cmd, targets = None):
        """Run the varassign command."""
        if not targets:
            targets = self.comm.get_mpiranks()
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
            self.comm.send(GDBMessage(CMD_MSG,
                                      command = Command("var-assign",
                                                        args = ('"' + full_name + '"', '"' + val + '"')),
                                      ranks = rank),
                           rank)

    def do_help(self, cmd, targets = None):
        """Run the help command."""
        if not targets:
            # Because this makes the most sense, unless told otherwise, we run this on one processor.
            targets = 0
        self.comm.send(GDBMessage(CMD_MSG, command = Command("interpreter-exec",
                                                             args = ("console", '"help ' + cmd + '"')),
                                  ranks = targets),
                       targets)

    def do_kill(self, cmd, targets = None):
        """Kill all targets being debugged."""
        # This always sends to all targets, for now.
        print "Sending SIGTERM to all inferiors. (May need to step them for them to die.)"
        self.comm.send(GDBMessage(KILL_MSG), self.comm.broadcast)

    def do_quit(self, cmd, targets = None):
        """Gracefully quit PGDB."""
        self.quit = True
        self.comm.send(GDBMessage(CMD_MSG, command = Command("gdb-exit")), self.comm.broadcast)

    def do_expand(self, cmd, targets = None):
        """Expand output.

        Use: [proc <processor-spec>] expand [history-item]
        Expand history-item for the given processors.

        """
        if not targets:
            targets = self.comm.get_mpiranks()
        split = cmd.split(" ")
        history_item = 0
        if len(split) > 1:
            if not split[1].isdigit():
                print "Incorrect history specificiation."
                return
            history_item = int(split[1])
        if history_item >= len(self.output_history):
            print "No such history item {0}".format(history_item)
            return
        arec = self.output_history[history_item]
        # We only care about the IDs that are present in both.
        ids = targets.intersect(arec.get_ranks())
        for vid in ids:
            self.pprinter.pretty_print(arec.get_record(vid), Interval(vid))

    def dispatch_gdbmi_command(self, command):
        """Send a GDB command to every rank (use proc to send to subsets)."""
        if self.comm.is_shutdown():
            return False
        return self.comm.send(GDBMessage(CMD_MSG, command = command),
                              self.comm.broadcast)

    def handle_msg(self, msg):
        """Handle a received message."""
        if msg.msg_type in self.msg_handlers:
            self.msg_handlers[msg.msg_type](msg)
        else:
            print "Got a message {0} with no handler.".format(msg.msg_type)

    def remote_body(self):
        """The main remote body thread.

        This initializes the remote infrastructure, and receives and processes data.

        """
        # Must do the init inside of this thread, or else LaunchMON steals stdin.
        if not self.remote_init():
            return False
        # Signal main thread we can use stdin.
        self.remote_up.set()
        print "PGDB deployed to {0} hosts and {1} processors.".format(
            self.comm.get_mrnet_network_size(),
            self.comm.get_proctab_size())
        recvd = False
        while not self.quit and not self.comm.all_nodes_exited():
            # Receive data, if any.
            msg = self.comm.recv(blocking = False)
            if msg is not None:
                # Received data.
                self.handle_msg(msg)
                recvd = True
            else:
                recvd = False

            # Keep from beating up the CPU too much.
            if not recvd:
                self.process_out_messages()
                time.sleep(self.sleep_time)
        self.shutdown()
        print "Remote shut down."
        self.interrupt_main()

    def local_body(self):
        """The local command input loop."""
        # Wait until we can use stdin.
        try:
            self.remote_up.wait()
            os.dup2(self.stdin_copy, 0)
            os.close(self.stdin_copy)
            self.cmdloop()
        except KeyboardInterrupt:
            print "Terminating."
            sys.exit(0)

    def run(self):
        """Start the remote thread and run the local command input loop."""
        self.parse_args()
        # This is part of a hack to keep LaunchMON from stealing stdin.
        self.stdin_copy = os.dup(0)
        os.close(0)
        self.remote_thread = threading.Thread(target = self.remote_body)
        self.remote_thread.daemon = True
        self.remote_thread.start()
        self.local_body()
