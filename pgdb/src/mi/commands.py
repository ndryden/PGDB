"""Main file implementing GDB Machine Interface commands."""

# This is deprecated as of 2.7, but we need to support 2.6.
import optparse

class Command(object):
    """Represents a GDB machine interface command and associated arguments."""

    def __init__(self, command, opts = None, args = None):
        """Initialize a command.

        command is the command.
        opts is a dictionary of key-value options.
        args is a list of positional arguments.

        """
        self.command = command
        self.opts = opts
        if not self.opts:
            self.opts = {}
        self.args = args
        if not self.args:
            self.args = []
        self.annotations = None

    def generate_mi_command(self):
        """Generate a machine interface command from this Command."""
        return "-" + self.command + " " + " ".join(map(lambda (k, v): k + " " + v, self.opts.items())) + " " + " ".join(self.args)

class Commands(object):
    """Represents the set of commands a GDB MI supports."""

    def __init__(self):
        """Sets up the set of MI commands, completions, and such."""
        # These are the actual machine interface command names.
        self.canonical_mi_commands = [
            # Breakpoints.
            "break-after",
            "break-commands",
            "break-condition",
            "break-delete",
            "break-disable",
            "break-enable",
            "break-info",
            "break-insert",
            "break-list",
            "break-passcount",
            "break-watch",
            # Environment.
            "exec-arguments",
            "environment-cd",
            "environment-directory",
            "environment-path",
            "environment-pwd",
            # Threads.
            "thread-info",
            "thread-list-ids",
            "thread-select",
            # Execution.
            "exec-continue",
            "exec-finish",
            "exec-interrupt",
            "exec-jump",
            "exec-next",
            "exec-next-instruction",
            "exec-return",
            "exec-run",
            "exec-step",
            "exec-step-instruction",
            "exec-until",
            # Stack manipulation.
            "stack-info-frame",
            "stack-info-depth",
            "stack-list-arguments",
            "stack-list-frames",
            "stack-list-locals",
            "stack-list-variables",
            "stack-select-frame",
            # Variable objects.
            "enable-pretty-printing",
            "var-create",
            "var-delete",
            "var-set-format",
            "var-show-format",
            "var-info-num-children",
            "var-list-children",
            "var-info-type",
            "var-info-expression",
            "var-info-path-expression",
            "var-show-attributes",
            "var-evaluate-expression",
            "var-assign",
            "var-update",
            "var-set-frozen",
            "var-set-update-range",
            "var-set-visualizer",
            # Data manipulation.
            "data-disassemble",
            "data-evaluate-expression",
            "data-list-changed-registers",
            "data-list-register-names",
            "data-list-register-values",
            "data-read-memory-bytes",
            "data-write-memory-bytes",
            # Tracepoints.
            "trace-find",
            "trace-define-variable",
            "trace-save",
            "trace-start",
            "trace-status",
            "trace-stop",
            # Symbol query.
            "symbol-list-lines",
            # File commands.
            "file-exec-and-symbols",
            "file-exec-file",
            "file-list-exec-source-file",
            "file-list-exec-source-files",
            "file-symbol-file",
            # Target manipulation.
            "target-attach",
            "target-detach",
            "target-disconnect",
            "target-download",
            "target-select",
            # File transfer.
            "target-file-put",
            "target-file-get",
            "target-file-delete",
            # Miscellaneous.
            "gdb-exit",
            "gdb-set",
            "gdb-show",
            "gdb-version",
            "list-features",
            "list-target-features",
            "list-thread-groups",
            "info-os",
            "add-inferior",
            "interpreter-exec",
            "inferior-tty-set",
            "inferior-tty-show",
            "enable-timings"
            ]
        # These are aliases for MI commands.
        self.command_aliases = {
            # Breakpoints.
            "ignore": "break-after",
            "commands": "break-commands",
            "condition": "break-condition",
            "delete": "break-delete",
            "disable": "break-disable",
            "enable": "break-enable",
            "info break": "break-info",
            "break": "break-insert",
            "tbreak": "break-insert",
            "hbreak": "break-insert",
            "thbreak": "break-insert",
            "list break": "break-list",
            "passcount": "break-passcount",
            "watch": "break-watch",
            "awatch": "break-watch",
            "rwatch": "break-watch",
            # Environment.
            "set args": "exec-arguments",
            "cd": "environment-cd",
            "dir": "environment-dir",
            "path": "environment-path",
            "pwd": "environment-pwd",
            # Threads.
            "info thread": "thread-info",
            "list thread ids": "thread-list-ids",
            "thread": "thread-select",
            # Execution.
            "continue": "exec-continue",
            "finish": "exec-finish",
            "interrupt": "exec-interrupt",
            "jump": "exec-jump",
            "next": "exec-next",
            "nexti": "exec-next-instruction",
            "return": "exec-return",
            "run": "exec-run",
            "step": "exec-step",
            "stepi": "exec-step-instruction",
            "until": "exec-until",
            # Stack manipulation.
            "info frame": "stack-info-frame",
            "info stack depth": "stack-info-depth",
            "list stack arguments": "stack-list-arguments",
            "backtrace": "stack-list-frames",
            "where": "stack-list-frames",
            "list locals": "stack-list-locals",
            "info locals": "stack-list-variables",
            "list variables": "stack-list-variables",
            "frame": "stack-select-frame",
            # Variable objects.
            # (No aliases.)
            # Data manipulation.
            "disassemble": "data-disassemble",
            "print": "data-evaluate-expression",
            "output": "data-evaluate-expression",
            "call": "data-evaluate-expression",
            "list changed registers": "data-list-changed-registers",
            "list register names": "data-list-register-names",
            "info registers": "data-list-register-values",
            "info all-reg": "data-list-register-values",
            "x": "data-read-memory-bytes",
            "write memory bytes": "data-write-memory-bytes",
            # Tracepoints.
            "tfind": "trace-find",
            "tvariable": "trace-define-variable",
            "tvariables": "trace-list-variables",
            "tsave": "trace-save",
            "tstart": "trace-start",
            "tstatus": "trace-status",
            "tstop": "trace-stop",
            # Symbol query.
            "list symbol lines": "symbol-list-lines",
            # File commands.
            "file": "file-exec-and-symbols",
            "exec-file": "file-exec-file",
            "info source": "file-list-exec-source-file",
            "info sources": "file-list-exec-source-files",
            "symbol-file": "file-symbol-file",
            # Target manipulation.
            "attach": "target-attach",
            "detach": "target-detach",
            "disconnect": "target-disconnect",
            "load": "target-download",
            "target": "target-select",
            # File transfer.
            "remote put": "target-file-put",
            "remote get": "target-file-get",
            "remote delete": "target-file-delete",
            # Miscellaneous.
            "quit": "gdb-exit",
            "set": "gdb-set",
            "show": "gdb-show",
            "show version": "gdb-version",
            "set inferior-tty": "set-inferior-tty",
            "show inferior-tty": "show-inferior-tty"
            }
        # These are options that every command takes. This is a list of tuples with the first value
        # the option and the second value the value to pass to "action".
        self.global_options = [
            ("--thread", "store"),
            ("--frame", "store")
            ]
        # This is the set of options for particular canonical commands.
        self.options = {
            "break-insert": [("-t", "store_true"),
                             ("-h", "store_true"),
                             ("-f", "store_true"),
                             ("-d", "store_true"),
                             ("-a", "store_true"),
                             ("-c", "store"),
                             ("-i", "store"),
                             ("-p", "store")],
            "break-watch": [("-a", "store_true"),
                            ("-r", "store_true")],
            "environment-dir": [("-r", "store_true")],
            "environment-path": [("-r", "store_true")],
            "exec-continue": [("--reverse", "store_true"),
                              ("--all", "store_true"),
                              ("--thread-group", "store")],
            "exec-finish": [("--reverse", "store_true")],
            "exec-interrupt": [("--all", "store_true"),
                               ("--thread-group", "store")],
            "exec-next": [("--reverse", "store_true")],
            "exec-next-instruction": [("--reverse", "store_true")],
            "exec-run": [("--all", "store_true"),
                         ("--thread-group", "store")],
            "exec-step": [("--reverse", "store_true")],
            "exec-step-instruction": [("--reverse", "store_true")],
            "var-delete": [("-c", "store_true")],
            "var-evaluate-expression": [("-f", "store_true")],
            "data-disassemble": [("-s", "store"),
                                 ("-e", "store"),
                                 ("-f", "store"),
                                 ("-l", "store"),
                                 ("-n", "store")],
            "data-read-memory-bytes": [("-o", "store")],
            "trace-save": [("-r", "store_true")],
            "-list-thread-groups": [("--available", "store_true"),
                                    ("--recurse", "store")]
            }
        # Pre-generate option parsers and maps for all commands and store in self.option_parsers/maps.
        self._generate_option_parsers()
        # This is the set of callbacks for canonical MI commands.
        self.canonical_callbacks = {}
        # This is the set of callbacks for alias commands.
        self.alias_callbacks = {}
        # This is the list searched for completions. Canonical MI commands are in here with
        # both their original name and hyphens replaced with spaces. Aliases are in here verbatim.
        self.completions = self.canonical_mi_commands + map(lambda x: x.replace("-", " "),
                                                            self.canonical_mi_commands) + self.command_aliases.keys()

    def _generate_default_optparser(self):
        """Generate a default option parser using the global options only."""
        parser = optparse.OptionParser(conflict_handler = "resolve")
        for opt, action in self.global_options:
            parser.add_option(opt, action = action)
        return parser

    def _generate_optparser(self, options):
        """Generate an option parser based on the provided options.

        options is a list of tuples in the same format as self.global_options.

        """
        parser = self._generate_default_optparser()
        for opt, action in options:
            parser.add_option(opt, action = action)
        return parser

    def _generate_option_parsers(self):
        """Generate and store option parsers and maps for all commands."""
        self.option_parsers = {}
        self.option_maps = {}
        for cmd in self.canonical_mi_commands:
            self.option_maps[cmd] = {}
            if cmd in self.options:
                self.option_parsers[cmd] = self._generate_optparser(self.options[cmd])
            else:
                self.option_parsers[cmd] = self._generate_default_optparser()
            for opt in self.option_parsers[cmd].option_list:
                self.option_maps[cmd][opt.get_opt_string().strip("-").replace("-", "_")] = opt.get_opt_string()

    def _optparse_to_dict(self, command, opts):
        """Take an object returned by parse_args and turn it into a dictionary."""
        options = {}
        for opt, val in vars(opts).items():
            if val:
                options[self.option_maps[command][opt]] = val
        return options

    def complete(self, string):
        """Attempt to determine if there is a unique completion for in the commands for a string.

        Returns the unique completion for a given string, or False if there is not one.

        """
        matches = []
        length = len(string)
        for completion in self.completions:
            if completion[0:length] == string:
                if completion == string:
                    # If we have an exact match, just return it.
                    return completion
                matches.append(completion)
        if len(matches) == 1:
            return matches[0]
        return False

    def _split_command(self, string):
        """Given a string, split it into the command and arguments."""
        split = string.split()
        cmd = ""
        while len(split):
            complete = self.complete(cmd)
            if not complete:
                cmd += split.pop(0)
            else:
                return complete, split
        complete = self.complete(cmd)
        if not complete:
            # Command not found.
            return None
        return complete, split

    def generate_command(self, string):
        """Generate a command object based upon a string.

        This works as follows:
        First, the command name is determined:
        - Words are gobbled up from the start of the string (a word is text separated by spaces).
        - The first command that matches, based upon the complete() command, is chosen.
        If the command is not found, return None.
        Next, callbacks are invoked as follows:
        - If the command is a canonical command, a command object is generated. If there is a callback,
        it is invoked with the command object, then the modified command object is returned.
        - If the command is an alias command, a command object is generated containing just the name
        of the command. If there is an alias callback, it is invoked with that command object and the
        rest of the input string. That callback should fill out any options in the command object that
        it needs to, and should return what is left of the input string to parse. The returned input
        string is parsed for options, which are added to the command object. The command in the command
        object is adjusted to be the canonical command. If there is a canonical callback, it is now
        invoked, and the final command object is returned.

        """
        # Determine the command name.
        split = self._split_command(string)
        if not split:
            return None
        cmd, rest = split
        if cmd in self.canonical_mi_commands:
            opts, args = self.option_parsers[cmd].parse_args(rest)
            command = Command(cmd, opts = self._optparse_to_dict(cmd, opts), args = args)
            if cmd in self.canonical_callbacks:
                self.canonical_callbacks[cmd](command)
            return command
        elif cmd in self.command_aliases:
            canonical = self.command_aliases[cmd]
            command = Command(cmd)
            if cmd in self.alias_callbacks:
                rest = self.alias_callbacks(command, rest)
            if rest:
                opts, args = self.option_parsers[canonical].parse_args(rest)
                command.opts.update(self._optparse_to_dict(canonical, opts))
                command.args += args
            command.command = canonical
            return command
        else:
            # Something went wrong, we should never get here.
            print "Completed a command but it's not a canonical or an alias! Got '{0}'.".format(cmd)
            return None
