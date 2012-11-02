"""Some useful interfaces for the front-end side of things interfacing with the GDB machine interface."""

import cmd
import optparse
import os
import sys
from mpi4py import MPI
from gdbmi import *

class GDBMICmd (cmd.Cmd):
    """Simple extension of Cmd for controlling GDB."""
    prompt = ""
    intro = ""

    def __init__(self):
        """Initialize Cmd and load the commands."""
        cmd.Cmd.__init__(self)
        self.use_rawinput = 1
        self.completekey = "tab"
        self.load_cmds()

    def do_EOF(self, line):
        """Terminate."""
        return True

    def _gen_parser(self):
        """Generate a default option parser."""
        # Note: Optparse is deprecated starting in Python 2.7/3.
        # But the replacement is only in >=2.7/3.
        parser = optparse.OptionParser(conflict_handler = "resolve")
        # These are supported by all commands.
        parser.add_option("--thread", action = "store")
        parser.add_option("--frame", action = "store")
        parser.add_option("--processor", action="store")
        return parser

    def _cmd_option_gen(self, gdbmi_cmd, options = None):
        """Generate a tuple for storing in the internal commands list.
        Options is a list of tuples in the format (option, action),
        to be used in optparse.
        Also adds the options to the option map."""
        parser = self._gen_parser()
        if options:
            for (k, action) in options:
                self.option_map[k.strip("-").replace("-", "_")] = k
                parser.add_option(k, action = action)
        return (gdbmi_cmd, parser)

    def load_cmds(self):
        """Set up the default option map and set of commands.
        Note that this set of commands is only the ones that need special
        handling due to having options."""
        # These are the current default ones.
        self.option_map = {
            "thread": "--thread",
            "frame": "--frame"
            }
        self.cmds = {
            "break": self._cmd_option_gen("bt_break",
                                          [("-t", "store_true"),
                                           ("-h", "store_true"),
                                           ("-f", "store_true"),
                                           ("-d", "store_true"),
                                           ("-a", "store_true"),
                                           ("-c", "store"),
                                           ("-i", "store"),
                                           ("-p", "store")]),
            "watch": self._cmd_option_gen("watch",
                                          [("-a", "store_true"),
                                           ("-r", "store_true")]),
            "dir": self._cmd_option_gen("dir",
                                        [("-r", "store_true")]),
            "path": self._cmd_option_gen("path",
                                         [("-r", "store_true")]),
            "continue": self._cmd_option_gen("cont",
                                             [("--reverse", "store_true"),
                                              ("--all", "store_true"),
                                              ("--thread-group", "store")]),
            "finish": self._cmd_option_gen("finish",
                                           [("--reverse", "store_true")]),
            "interrupt": self._cmd_option_gen("interrupt",
                                              [("--all", "store_true"),
                                               ("--thread-group", "store")]),
            "next": self._cmd_option_gen("next",
                                         [("--reverse", "store_true")]),
            "nexti": self._cmd_option_gen("nexti",
                                          [("--reverse", "store_true")]),
            "run": self._cmd_option_gen("run",
                                        [("--all", "store_true"),
                                         ("--thread-group", "store")]),
            "step": self._cmd_option_gen("step",
                                         [("--reverse", "store_true")]),
            "stepi": self._cmd_option_gen("stepi",
                                          [("--reverse", "store_true")]),
            "var_delete": self._cmd_option_gen("var_delete",
                                               [("-c", "store_true")]),
            "var_evaluate_expression": self._cmd_option_gen("var_evaluate_expression",
                                                            [("-f", "store_true")]),
            "disassemble": self._cmd_option_gen("disassemble",
                                                [("-s", "store"),
                                                 ("-e", "store"),
                                                 ("-f", "store"),
                                                 ("-l", "store"),
                                                 ("-n", "store")]),
            "print": self._cmd_option_gen("output"),
            "x": self._cmd_option_gen("x",
                                      [("-o", "store")]),
            "tsave": self._cmd_option_gen("tsave",
                                          [("-r", "store_true")]),
            "list_thread_groups": self._cmd_option_gen("list_thread_groups",
                                                       [("--available", "store_true"),
                                                        ("--recurse", "store")])
            }

    def dispatch_gdbmi_command(self, gdbmi_cmd, args, options):
        """Execute a GDBMI command. Should be over-ridden by children."""
        print "Would call " + gdbmi_cmd + " with arguments " + str(args) + " and options " + str(options)

    def check_gdbmi_command(self, gdbmi_cmd):
        """Check whether a name is a GDBMI command. Should be over-ridden by
        children."""
        print "Checking " + gdbmi_cmd
        return False

    def run(self):
        """Main run loop. Should be over-ridden by children if needed."""
        self.cmdloop()

    def resolve_gdbmi_command(self, line, err = True):
        """Parse a line into a GDBMI command."""
        cmd, arg, line = self.parseline(line)
        if cmd is None:
            if err:
                print "Bad line: {0}".format(line)
            return None, None, None
        split = arg.split()
        # Attempt to determine the actual command by gobbling up the arguments.
        while cmd not in self.cmds and not self.check_gdbmi_command(cmd) and len(split) > 0:
            cmd += "_" + split.pop(0)
        if cmd not in self.cmds and not self.check_gdbmi_command(cmd):
            if err:
                print "Bad command: " + line
            return None, None, None
        if cmd in self.cmds:
            (cmd, parser) = self.cmds[cmd]
        else:
            # Generate a default parser.
            parser = self._gen_parser()
        (opts, arg) = parser.parse_args(split)
        options = []
        for opt, val in vars(opts).items():
            if val is not None:
                options.append(self.option_map[opt])
                if type(val) is not bool:
                    options.append(val)
        return cmd, arg, options

    def default(self, line):
        """Called when the cmdloop can't find the command. This catches
        and handles all the GDBMI commands."""
        cmd, arg, options = self.resolve_gdbmi_command(line)
        if cmd:
            self.dispatch_gdbmi_command(cmd, arg, options)
