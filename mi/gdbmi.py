"""An interface to GDB using its Machine Interface."""

import subprocess
import fcntl
import os
import select
import re
from gdbmi_parser import *

def pretty_print_record(record):
    """A conenience duplication from the main pretty-printer, to print a record."""
    if record.record_type == RESULT:
        print "[{0}] ({1}): result_class = {2}, results = {3}".format(record.token, record.record_type, record.result_class, record.results)
    elif (record.record_type == ASYNC_EXEC) or (record.record_type == ASYNC_STATUS) or (record.record_type == ASYNC_NOTIFY):
        print "[{0}] ({1}): output_class = {2}, output = {3}".format(record.token, record.record_type, record.output_class, record.output)
    elif (record.record_type == STREAM_CONSOLE) or (record.record_type == STREAM_TARGET) or (record.record_type == STREAM_LOG):
        print "[NONE] ({0}): {1}".format(record.record_type, record.string)
    elif record.record_type == UNKNOWN:
        print "Unknown record: {0}".format(record.output)
    else:
        print "Unknown record: {0}".format(record.record_type)

class GDBMachineInterface:
    """Manages the GDB Machine Interface."""

    def __init__(self, target = None, attach = False, gdb = "gdb", gdb_args = [], 
                 default_handler = None):
        """Initialize a new machine interface session with GDB."""
        self.target = target
        self.do_attach = attach
        self.process = subprocess.Popen(
            args = [gdb, '--quiet', '--nx', '--nw', '--interpreter=mi2'] + gdb_args,
            stdin = subprocess.PIPE,
            stdout = subprocess.PIPE,
            close_fds = True,
            env = os.environ
            )
        f = fcntl.fcntl(self.process.stdout, fcntl.F_GETFL)
        fcntl.fcntl(self.process.stdout, fcntl.F_SETFL, f | os.O_NONBLOCK)

        # Possibly override the default handler.
        if default_handler:
            self._default_handler = default_handler
        else:
            self._default_handler = self._internal_handler

        self.token = 0 # This is used to identify associated output.
        self.handlers = {} # Callbacks based on tokens.
        self.buffer = "" # Buffer for output from GDB.
        self.parser = GDBMIParser() # Parser for output from GDB.
        self.commands = {} # GDB commands.
        self._register_default_commands()

    def _read(self, timeout = 0):
        """A generator to read data from GDB's stdout."""
        while True:
            # Some notes: This probably doesn't work on Windows.
            # On Linux, using epoll would be faster.
            # On BSD, using kqueue would be faster.
            ready = select.select([self.process.stdout], [], [], timeout)
            if not ready[0]:
                # No data to read.
                break
            try:
                yield self.process.stdout.read()
                timeout = 0 # This way we don't block on subsequent reads while there is data.
            except IOError:
                break

    def _write(self, data):
        """Write data to GDB."""
        self.process.stdin.write(data + "\n")
        self.process.stdin.flush()

    def send(self, command, handler = None, token = None):
        """Send data to GDB and return the associated token.
        Takes an optional handler to handle the response."""
        if not token:
            token = self.token
            token_str = "{0:08d}".format(self.token)
            self.token += 1
        else:
            token_str = str(token)
        self.handlers[token] = handler
        self._write(token_str + command)
        return token

    def _command_generator(self, mi_command, default_handler = None, default_args = ()):
        """ Generates a command to send a GDBMI command.
        mi_command is the MI command, suitable for string.format for filling in
        positional arguments.
        default_args is a tuple of default arguments; any positional
        arguments that are not provided are taken from that.
        The returned command will take normal arguments for positional
        arguments.
        The options parameter, if provided, is a list of options that
        are appended to the MI command."""
        if not default_handler:
            default_handler = self._default_handler
        def _gdbmi_cmd(*args, **kwds):
            args = args + default_args[len(args):]
            args = map(str, args)
            if not "handler" in kwds:
                kwds["handler"] = default_handler
            options = ""
            token = None
            if "options" in kwds:
                if kwds["options"]:
                    options = " " + " ".join(kwds["options"])
            if "token" in kwds:
                token = kwds["token"]
            try:
                command = mi_command.format(" ".join(args), options = options)
                self.send(command, token = token, handler = kwds["handler"])
            except IndexError:
                print "Bad arguments."
        return _gdbmi_cmd

    def add_gdb_command(self, name, mi_command, default_handler = None, default_args = ()):
        """Add a GDB command and make it callable with self.name."""
        cmd = self._command_generator(mi_command, default_handler = default_handler, default_args = default_args)
        self.commands[name] = cmd

    def __getattr__(self, name):
        """Getter to support command execution."""
        if not name in self.commands:
            raise AttributeError()
        return self.commands[name]

    def _internal_handler(self, record):
        """Default handler for records."""
        pretty_print_record(record)
        return True

    def _handle(self, record):
        """Internal function to handle data."""
        if record.token is not None and self.handlers[record.token]:
            return self.handlers[record.token](record)
        else:
            return self._default_handler(record)

    def read(self, timeout = 0):
        """Generator to read data from GDB, call appropriate handlers, and
        return the data read."""
        for data in self._read(timeout):
            self.buffer += data
            while True:
                (before, nl, self.buffer) = self.buffer.rpartition("\n")
                if nl:
                    (oob_records, result_records) = self.parser.parse_output(before)
                    for oob_record in oob_records:
                        if self._handle(oob_record):
                            yield oob_record
                    for result_record in result_records:
                        if self._handle(result_record):
                            yield result_record
                else:
                    #self.buffer = before
                    return

    def start(self, arguments = ""):
        """Helper function to start the targetted executable."""
        if not self.target:
            return
        if self.do_attach:
            self.attach(self.target)
        else:
            self.file(self.target)
            self.run(arguments)

    def is_running(self):
        """Check if the GDB process is running."""
        return self.process.poll() is None

    def _register_default_commands(self):
        """Register all the default commands, which is basically the entire
        set of commands supported by the MI."""
        # Breakpoints.
        self.add_gdb_command("ignore", "-break-after {options} {0}")
        self.add_gdb_command("commands", "-break-commands {options} {0}", default_args = ("BAD", ""))
        self.add_gdb_command("condition", "-break-condition {options} {0}")
        self.add_gdb_command("delete", "-break-delete {options} {0}")
        self.add_gdb_command("disable", "-break-disable {options} {0}")
        self.add_gdb_command("enable", "-break-enable {options} {0}")
        self.add_gdb_command("info_break", "-break-info {options} {0}", default_args = ("",))
        self.add_gdb_command("bt_break", "-break-insert {options} {0}", default_args = ("",))
        self.add_gdb_command("list_break", "-break-list {options}")
        self.add_gdb_command("passcount", "-break-passcount {options} {0}")
        self.add_gdb_command("watch", "-break-watch {options} {0}", default_args = ("",))
        self.add_gdb_command("awatch", "-break-watch -a {options} {0}", default_args = ("",))
        self.add_gdb_command("rwatch", "-break-watch -r {options} {0}", default_args = ("",))
        # Environment.
        self.add_gdb_command("set_args", "-exec-arguments {options} {0}")
        self.add_gdb_command("cd", "-environment-cd {options} {0}")
        self.add_gdb_command("dir", "-environment-directory {options} {0}")
        self.add_gdb_command("path", "-environment-path {options} {0}")
        self.add_gdb_command("pwd", "-environment-pwd {options}")
        # Threads.
        self.add_gdb_command("info_thread", "-thread-info {options} {0}", default_args = ("",))
        self.add_gdb_command("thread", "-thread-select {options} {0}")
        # Execution.
        self.add_gdb_command("cont", "-exec-continue {options}")
        self.add_gdb_command("finish", "-exec-finish {options}")
        self.add_gdb_command("interrupt", "-exec-interrupt {options}")
        self.add_gdb_command("jump", "-exec-jump {options} {0}")
        self.add_gdb_command("next", "-exec-next {options}")
        self.add_gdb_command("nexti", "-exec-next-instruction {options}")
        self.add_gdb_command("ret", "-exec-return {options}")
        self.add_gdb_command("run", "-exec-run {options} {0}", default_args = ("",))
        self.add_gdb_command("step", "-exec-step {options}")
        self.add_gdb_command("stepi", "-exec-step-instruction {options}")
        self.add_gdb_command("until", "-exec-until {options} {0}", default_args = ("",))
        # Stack manipulation.
        self.add_gdb_command("info_frame", "-stack-info-frame {options}")
        self.add_gdb_command("info_stack_depth", "-stack-info-depth {options} {0}", default_args = ("",))
        self.add_gdb_command("list_stack_arguments", "-stack-list-arguments {options} {0}", default_args = ("BAD", "", ""))
        self.add_gdb_command("backtrace", "-stack-list-frames {options} {0}", default_args = ("", ""))
        self.add_gdb_command("info_locals", "-stack-list-locals {options} {0}")
        self.add_gdb_command("list_stack_variables", "-stack-list-variables {options} {0}")
        # Note: this is deprecated in favour of using --frame.
        self.add_gdb_command("frame", "-stack-select-frame {options} {0}")
        # Variable objects.
        self.add_gdb_command("enable_pretty_printing", "-enable-pretty-printing {options}")
        self.add_gdb_command("var_create", "-var-create {options} {0}")
        self.add_gdb_command("var_delete", "-var-delete {options} {0}")
        self.add_gdb_command("var_set_format", "-var-set-format {options} {0}")
        self.add_gdb_command("var_show_format", "-var-show-format {options} {0}")
        self.add_gdb_command("var_info_num_children", "-var-info-num-children {options} {0}")
        self.add_gdb_command("var_list_children", "-var-list-children {options} {0}", default_args = ("", "", ""))
        self.add_gdb_command("var_info_type", "-var-info-type {options} {0}")
        self.add_gdb_command("var_info_expression", "-var-info-expression {options} {0}")
        self.add_gdb_command("var_info_path_expression", "-var-info-path-expression {options} {0}")
        self.add_gdb_command("var_show_attributes", "-var-show-attributes {options} {0}")
        self.add_gdb_command("var_evaluate_expression", "-var-evaluate-expression {options} {0}")
        self.add_gdb_command("var_assign", "-var-assign {options} {0}")
        self.add_gdb_command("var_update", "-var-update {options} {0}", default_args = ("", ""))
        self.add_gdb_command("var_set_frozen", "-var-set-frozen {options} {0}")
        self.add_gdb_command("var_set_update_range", "-var-set-update-range {options} {0}")
        self.add_gdb_command("var_set_visualizer", "-var-set-visualizer {options} {0}")
        # Data manipulation.
        self.add_gdb_command("disassemble", "-data-disassemble {options} -- {0}")
        self.add_gdb_command("output", "-data-evaluate-expression {options} \"{0}\"")
        self.add_gdb_command("list_changed_registers", "-data-list-changed-registers {options}")
        self.add_gdb_command("list_register_names", "-data-list-register-names {options} {0}", default_args = ("",))
        self.add_gdb_command("info_reg", "-data-list-register-values {options} {0}", default_args = ("BAD", ""))
        self.add_gdb_command("x", "-data-read-memory-bytes {options} {0}")
        self.add_gdb_command("write_memory_bytes", "-data-write-memory-bytes {options} {0}")
        # Tracepoints.
        self.add_gdb_command("tfind", "-trace-find {options} {0}", default_args = ("BAD", ""))
        self.add_gdb_command("tvariable", "-trace-define-variable {options} {0}", default_args = ("BAD", ""))
        self.add_gdb_command("tvariables", "-trace-list-variables {options}")
        self.add_gdb_command("tsave", "-trace-save {options} {0}")
        self.add_gdb_command("tstart", "-trace-start {options}")
        self.add_gdb_command("tstatus", "-trace-status {options}")
        self.add_gdb_command("tstop", "-trace-stop {options}")
        # Symbol query.
        self.add_gdb_command("list_symbol_lines", "-symbol-list-lines {options} {0}")
        # File commands.
        self.add_gdb_command("file", "-file-exec-and-symbols {options} {0}")
        self.add_gdb_command("exec_file", "-file-exec-file {options} {0}")
        self.add_gdb_command("info_source", "-file-list-exec-source-file {options}")
        self.add_gdb_command("info_sources", "-file-list-exec-source-files {options}")
        self.add_gdb_command("symbol_file", "-file-symbol-file {options} {0}")
        self.add_gdb_command("attach", "-target-attach {options} {0}")
        self.add_gdb_command("detach", "-target-detach {options} {0}", default_args = ("",))
        self.add_gdb_command("disconnect", "-target-disconnect {options}")
        self.add_gdb_command("load", "-target-download {options}")
        self.add_gdb_command("target", "-target-select {options} {0}")
        # File transfer.
        self.add_gdb_command("remote_put", "-target-file-put {options} {0}")
        self.add_gdb_command("remote_get", "-target-file-get {options} {0}")
        self.add_gdb_command("remote_delete", "-target-file-delete {options} {0}")
        # Miscellaneous.
        self.add_gdb_command("quit", "-gdb-exit {options}")
        self.add_gdb_command("set", "-gdb-set {options} {0}")
        self.add_gdb_command("show", "-gdb-show {options} {0}")
        self.add_gdb_command("show_version", "-gdb-version {options}")
        self.add_gdb_command("list_features", "-list-features {options}")
        self.add_gdb_command("list_target_features", "-list-target-features {options}")
        self.add_gdb_command("list_thread_groups", "-list-thread-groups {options} {0}", default_args = ("",))
        self.add_gdb_command("info_os", "-info-os {options} {0}", default_args = ("",))
        self.add_gdb_command("add_inferior", "-add-inferior {options}")
        self.add_gdb_command("interpreter_exec", "-interpreter-exec {options} {0}")
        self.add_gdb_command("set_inferior_tty", "-inferior-tty-set {options} {0}")
        self.add_gdb_command("show_inferior_tty", "-inferior-tty-show {options}")
        self.add_gdb_command("enable_timings", "-enable-timings {options} {0}", default_args = ("",))
        
