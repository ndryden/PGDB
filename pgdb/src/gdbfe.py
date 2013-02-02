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
from comm import *
from mi.gdbmicmd import GDBMICmd
from mi.gdbmi_identifier import GDBMIRecordIdentifier
from mi.gdbmi_recordhandler import GDBMIRecordHandler
from mi.varobj import VariableObject, VariableObjectManager
from mi.commands import Command
from pprinter import GDBMIPrettyPrinter
from interval import Interval

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
            }
        # Now record handlers.
        self.record_handler = GDBMIRecordHandler(self.identifier)

    def remote_init(self):
        """Initialize things related to the remote communication and back-end daemons."""
        self.comm = CommunicatorFE(True) # Initialize with locking.
        # One of {pid} and {launcher, launcher_args} will not be none, based
        # upon the command line input parsing.
        self.comm.init_lmon(self.lmon_attach, pid = self.lmon_pid,
                            launcher = self.lmon_launcher,
                            launcher_args = self.lmon_launcher_argv)
        self.comm.init_mrnet()
        self.identifier = GDBMIRecordIdentifier()
        self.varobjs = {}
        for rank in self.comm.get_mpiranks():
            self.varobjs[rank] = VariableObjectManager()
        self.init_handlers()
        self.pprinter = GDBMIPrettyPrinter(self.identifier)
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

    def parse_args(self):
        """Parse the command-line arguments and set appropriate variables."""
        # Optparse unfortunately doesn't work here.
        self.lmon_attach = None
        self.lmon_pid = None
        self.lmon_launcher = None
        self.lmon_launcher_argv = None
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
                self.lmon_launcher_argv = sys.argv[i + 1:]
                break
        if self.lmon_attach is None:
            print "Arguments: (one of -p/--pid and -a is required)"
            print "-p, --pid <pid>: attach to srun process <pid>"
            print "-a <options>: pass <options> verbatim to the resource manager for launching."
            print "--launcher <launcher>: use binary <launcher> to launch."
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

    def parse_filter_spec(self, spec):
        """Parse a filter specification into a record type and class."""
        split = spec.lower().split()
        if len(split) == 0:
            print "Bad filter specification."
            return None, None
        record_type = split[0]
        record_class = None
        if len(split) > 1:
            record_class = split[1]
        return record_type, record_class

    def do_filter(self, cmd, targets = None):
        """Tell the back-end daemons to filter something."""
        record_type, record_class = self.parse_filter_spec(cmd)
        if not record_type:
            return
        self.comm.send(GDBMessage(FILTER_MSG, filter_type = record_type,
                                  filter_class = record_class),
                       self.comm.broadcast)

    def do_unfilter(self, cmd, targets = None):
        """Tell the back-end daemons to unfilter something."""
        record_type, record_class = self.parse_filter_spec(cmd)
        if not record_type:
            return
        self.comm.send(GDBMessage(UNFILTER_MSG, filter_type = record_type,
                                  filter_class = record_class),
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

    def dispatch_gdbmi_command(self, command):
        """Send a GDB command."""
        return self.comm.send(GDBMessage(CMD_MSG, command = command), self.comm.broadcast)

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
        self.remote_init()
        print "GDB deployed to {0} hosts and {1} processors.".format(self.comm.get_mrnet_network_size(),
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
                time.sleep(self.sleep_time)
        self.shutdown()
        thread.interrupt_main()

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
