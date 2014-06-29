"""A generic implementation of Cmd for use with GDB."""

from __future__ import print_function
import cmd
from commands import Commands

class GDBMICmd(cmd.Cmd):
    """Simple extension of Cmd for controlling GDB."""
    prompt = ""
    intro = ""

    def __init__(self):
        """Initialize Cmd and load the commands."""
        cmd.Cmd.__init__(self)
        self.use_rawinput = 1
        self.completekey = "tab"
        self.commands = Commands()

    def do_EOF(self, line):
        """Terminate."""
        return True

    def dispatch_gdbmi_command_string(self, string):
        """Dispatch a GDBMI command from a string."""
        command = self.resolve_gdbmi_command(string)
        if command:
            self.dispatch_gdbmi_command(cmd)

    def dispatch_gdbmi_command(self, command):
        """Execute a GDBMI command. Should be over-ridden by children."""
        print("Would invoke {0} with arguments {1} and options {2}".format(
            command.command,
            command.args,
            command.opts))

    def check_gdbmi_command(self, string):
        """Check whether a string is a valid command."""
        if self.commands.complete(string):
            return True
        return False

    def run(self):
        """Main run loop. Should be over-ridden by children if needed."""
        self.cmdloop()

    def resolve_gdbmi_command(self, line, err=True):
        """Parse a line into a GDBMI command."""
        command = self.commands.generate_command(line)
        if not command and err:
            print("Bad command: " + line)
        return command

    def default(self, line):
        """Catch and handle all GDBMI commands."""
        command = self.resolve_gdbmi_command(line)
        if command:
            self.dispatch_gdbmi_command(command)
