"""A simple wrapper for running one GDB instance locally for testing.

This simply starts a single GDB process, passes input through with relatively little command
parsing, and data out using the standard pretty-printer. A lot of the more fancy special commands
in the full interface are not available. This is primarily for testing things.

"""

import threading
from conf import gdbconf
from mi.gdbmi_front import *
from mi.gdbmi_identifier import GDBMIRecordIdentifier
from pprinter import GDBMIPrettyPrinter

class GDBMILocal (GDBMICmd):
    """Simple class for running one instance of GDB locally via the MI interface."""

    # Override the prompt from GDBMICmd and Cmd.
    prompt = ""

    def __init__(self, target):
        """Initialize GDBMICmd and load the machine interface, spawning GDB.
        
        target is presently unused.
        
        """
        GDBMICmd.__init__(self)
        ider = GDBMIRecordIdentifier()
        self.pprinter = GDBMIPrettyPrinter(ider)
        def handler(record):
            self.pprinter.pretty_print(record)
            return True
        self.gdb = GDBMachineInterface(target, gdb_args = ["-x", gdbconf.gdb_init_path],
                                       default_handler = handler)
        self.dispatch_gdbmi_command("enable_pretty_printing", (), {})

    def dispatch_gdbmi_command(self, gdbmi_cmd, args, options):
        """Over-ridden dispatch command to run GDBMI commands."""
        try:
            getattr(self.gdb, gdbmi_cmd)(*args, options = options)
        except AttributeError:
            print "Bad command: " + gdbmi_cmd

    def check_gdbmi_command(self, gdbmi_cmd):
        """Over-ridden check to check GDBMI commands."""
        try:
            getattr(self.gdb, gdbmi_cmd)
            return True
        except AttributeError:
            return False

    def read_thread(self):
        """Primary thread for reading from GDB.

        This repeatedly invokes the read command with a short pause, and relies upon the default
        handler we installed to handle printing.

        """
        while True:
            for rec in self.gdb.read(1):
                pass

    def run(self):
        """Over-ridden run. Sets up the read thread and starts it."""
        read_thread = threading.Thread(target = self.read_thread)
        read_thread.daemon = True
        read_thread.start()
        self.cmdloop()

gdb = GDBMILocal("")
gdb.run()
