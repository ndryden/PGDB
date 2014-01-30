"""A simple wrapper for running one GDB instance locally for testing.

This simply starts a single GDB process, passes input through with relatively little command
parsing, and data out using the standard pretty-printer. A lot of the more fancy special commands
in the full interface are not available. This is primarily for testing things.

"""

import threading
from conf import gdbconf
from mi.gdbmi import GDBMachineInterface
from mi.gdbmicmd import GDBMICmd
from mi.gdbmipprinter import GDBMIPrettyPrinter

class GDBMILocal (GDBMICmd):
    """Simple class for running one instance of GDB locally via the MI interface."""

    # Override the prompt from GDBMICmd and Cmd.
    prompt = ""

    def __init__(self):
        """Initialize GDBMICmd and load the machine interface, spawning GDB."""
        GDBMICmd.__init__(self)
        self.pprinter = GDBMIPrettyPrinter()
        self.gdb = GDBMachineInterface(gdb_args = ["-x", gdbconf.gdb_init_path])
        self.dispatch_gdbmi_command_string("enable-pretty-printing")

    def dispatch_gdbmi_command(self, command):
        """Over-ridden dispatch command to run GDBMI commands."""
        if self.gdb.is_running():
            self.gdb.send(command.generate_mi_command())

    def read_thread(self):
        """Primary thread for reading from GDB.

        This repeatedly invokes the read command with a short pause and pretty-prints the output.

        """
        while True:
            for record in self.gdb.read(1):
                self.pprinter.pretty_print(record)

    def run(self):
        """Over-ridden run. Sets up the read thread and starts it."""
        read_thread = threading.Thread(target = self.read_thread)
        read_thread.daemon = True
        read_thread.start()
        self.cmdloop()

gdb = GDBMILocal()
gdb.run()
