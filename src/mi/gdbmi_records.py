"""Record structures and constants for GDB/MI output."""

# Record constants.
RESULT = "RESULT"
ASYNC_EXEC = "EXEC"
ASYNC_STATUS = "STATUS"
ASYNC_NOTIFY = "NOTIFY"
STREAM_CONSOLE = "CONSOLE"
STREAM_TARGET = "TARGET"
STREAM_LOG = "LOG"
TERMINATOR = "TERM"
UNKNOWN = "UNKNOWN"
# Async record types.
ASYNC_EXEC_RUNNING = "running"
ASYNC_EXEC_STOPPED = "stopped"
# Async exec record stop reasons (record subtypes).
ASYNC_STOPPED_BREAKPOINT_HIT = "breakpoint-hit"
ASYNC_STOPPED_WATCHPOINT_TRIGGER = "watchpoint-trigger"
ASYNC_STOPPED_READ_WATCHPOINT_TRIGGER = "read-watchpoint-trigger"
ASYNC_STOPPED_ACCESS_WATCHPOINT_TRIGGER = "access-watchpoint-trigger"
ASYNC_STOPPED_FUNCTION_FINISHED = "function-finished"
ASYNC_STOPPED_LOCATION_REACHED = "location-reached"
ASYNC_STOPPED_WATCHPOINT_SCOPE = "watchpoint-scope"
ASYNC_STOPPED_END_STEPPING_RANGE = "end-stepping-range"
ASYNC_STOPPED_EXIT_SIGNALLED = "exit-signalled"
ASYNC_STOPPED_EXITED = "exited"
ASYNC_STOPPED_EXITED_NORMALLY = "exited-normally"
ASYNC_STOPPED_SIGNAL_RECEIVED = "signal-received"
ASYNC_STOPPED_SOLIB_EVENT = "solib-event"
ASYNC_STOPPED_FORK = "fork"
ASYNC_STOPPED_VFORK = "vfork"
ASYNC_STOPPED_SYSCALL_ENTRY = "syscall-entry"
ASYNC_STOPPED_SYSCALL_RETURN = "syscall-return"
ASYNC_STOPPED_EXEC = "exec"
# Async notify reasons (record subtypes).
ASYNC_NOTIFY_THREAD_GROUP_ADDED = "thread-group-added"
ASYNC_NOTIFY_THREAD_GROUP_REMOVED = "thread-group-removed"
ASYNC_NOTIFY_THREAD_GROUP_STARTED = "thread-group-started"
ASYNC_NOTIFY_THREAD_GROUP_EXITED = "thread-group-exited"
ASYNC_NOTIFY_THREAD_CREATED = "thread-created"
ASYNC_NOTIFY_THREAD_EXITED = "thread-exited"
ASYNC_NOTIFY_THREAD_SELECTED = "thread-selected"
ASYNC_NOTIFY_LIBRARY_LOADED = "library-loaded"
ASYNC_NOTIFY_LIBRARY_UNLOADED = "library-unloaded"
ASYNC_NOTIFY_TRACEFRAME_CHANGED = "traceframe-changed"
ASYNC_NOTIFY_TSV_CREATED = "tsv-created"
ASYNC_NOTIFY_TSV_DELETED = "tsv-deleted"
ASYNC_NOTIFY_TSV_MODIFIED = "tsv-modified"
ASYNC_NOTIFY_BREAKPOINT_CREATED = "breakpoint-created"
ASYNC_NOTIFY_BREAKPOINT_MODIFIED = "breakpoint-modified"
ASYNC_NOTIFY_BREAKPOINT_DELETED = "breakpoint-deleted"
ASYNC_NOTIFY_RECORD_STARTED = "record-started"
ASYNC_NOTIFY_RECORD_STOPPED = "record-stopped"
ASYNC_NOTIFY_CMD_PARAM_CHANGED = "cmd-param-changed"
ASYNC_NOTIFY_MEMORY_CHANGED = "memory-changed"
# Result record types.
RESULT_CLASS_DONE = "DONE"
RESULT_CLASS_RUNNING = "RUNNING"
RESULT_CLASS_CONNECTED = "CONNECTED"
RESULT_CLASS_ERROR = "ERROR"
RESULT_CLASS_EXIT = "EXIT"
# Result record subtypes.
RESULT_BREAKPOINT = "bkpt"
RESULT_BREAKPOINT_TABLE = "BreakpointTable"
RESULT_WATCHPOINT = "wpt"
RESULT_SOURCE_PATH = "source-path"
RESULT_PATH = "path"
RESULT_CWD = "cwd"
RESULT_THREADS = "threads"
RESULT_CURRENT_THREAD = "current-thread-id"
RESULT_THREAD_IDS = "thread-ids"
RESULT_NUMBER_OF_THREADS = "number-of-threads"
RESULT_NEW_THREAD_ID = "new-thread-id"
RESULT_FRAME = "frame"
RESULT_STACK_DEPTH = "depth"
RESULT_STACK_ARGS = "stack-args"
RESULT_STACK = "stack"
RESULT_LOCALS = "locals"
RESULT_VARIABLES = "variables"
RESULT_ASM = "asm_insns"
RESULT_VALUE = "value"
RESULT_CHANGED_REGISTERS = "changed-registers"
RESULT_REGISTER_NAMES = "register-names"
RESULT_REGISTER_VALUES = "register-values"
RESULT_MEMORY = "memory"
RESULT_TRACE_VARIABLES = "trace-variables"
RESULT_LINES = "lines"
RESULT_FILES = "files"
RESULT_LINE = "line"
RESULT_FILE = "file"
RESULT_FULLNAME = "fullname"
RESULT_MACRO_INFO = "macro-info"
RESULT_RESULT = "result"
RESULT_GROUPS = "groups"
RESULT_OS_DATA_TABLE = "OSDataTable"
RESULT_THREAD_GROUP = "thread-group"
RESULT_INFERIOR_TTY = "inferior_tty_terminal"
RESULT_TIME = "time"
RESULT_MSG = "msg"
RESULT_CODE = "code"

def _make_list(item):
    """Make item into a list if it is not."""
    if type(item) is list:
        return item
    return [item]

class GDBMIRecord(object):
    """The top-level GDB record class."""

    def __init__(self):
        """Initialize defaults for records."""
        self.record_type = None
        self.record_subtypes = set()
        self.token = None
        self.fields = []

    def pretty_print(self):
        """Default pretty printer for records."""
        return [str(self)]

    def __key(self):
        """Return a key defining the record."""
        l = [self.record_type] + list(self.record_subtypes) + [self.token]
        for field in self.fields:
            val = getattr(self, field)
            if isinstance(val, list):
                val = tuple(val)
            elif isinstance(val, dict):
                val = tuple(val.items())
            l.append(val)
        return tuple(l)

    def __eq__(self, other):
        """Equality check."""
        return self.__key() == other.__key()

    def __hash__(self):
        """Hash."""
        return hash(self.__key())

    def _str_fields(self):
        s = ""
        for field in self.fields:
            val = getattr(self, field)
            s += "{0} = {1}\n".format(field, val)
        return s

    def __repr__(self):
        """Simple repr that returns __str__ so that output is nicer."""
        return self.__str__()

class GDBMIAsyncRecord(GDBMIRecord):
    """An async record."""

    @staticmethod
    def create_record(record_type, token, output_class, output):
        """Create a new async record."""
        record = GDBMIAsyncRecord()
        record.record_type = record_type
        record.token = token
        record.record_subtypes.add(output_class)
        if "frame" in output:
            record.frame = GDBMIFrame(output["frame"])
            record.fields += ["frame"]
        if record_type == ASYNC_EXEC:
            record.thread_id = int(output["thread-id"])
            record.fields += ["thread_id"]
            if output_class == ASYNC_EXEC_STOPPED:
                record.reason = output.get("reason")
                if record.reason:
                    if ASYNC_STOPPED_BREAKPOINT_HIT == record.reason:
                        record.breakpoint_id = int(output["bkptno"])
                    elif ASYNC_STOPPED_WATCHPOINT_TRIGGER == record.reason:
                        pass
                    elif ASYNC_STOPPED_READ_WATCHPOINT_TRIGGER == record.reason:
                        pass
                    elif ASYNC_STOPPED_ACCESS_WATCHPOINT_TRIGGER == record.reason:
                        pass
                    elif ASYNC_STOPPED_FUNCTION_FINISHED == record.reason:
                        pass
                    elif ASYNC_STOPPED_LOCATION_REACHED == record.reason:
                        pass
                    elif ASYNC_STOPPED_WATCHPOINT_SCOPE == record.reason:
                        pass
                    elif ASYNC_STOPPED_END_STEPPING_RANGE == record.reason:
                        pass
                    elif ASYNC_STOPPED_EXIT_SIGNALLED == record.reason:
                        pass
                    elif ASYNC_STOPPED_EXITED == record.reason:
                        pass
                    elif ASYNC_STOPPED_EXITED_NORMALLY == record.reason:
                        pass
                    elif ASYNC_STOPPED_SIGNAL_RECEIVED == record.reason:
                        pass
                    elif ASYNC_STOPPED_SOLIB_EVENT == record.reason:
                        pass
                    elif ASYNC_STOPPED_FORK == record.reason:
                        pass
                    elif ASYNC_STOPPED_VFORK == record.reason:
                        pass
                    elif ASYNC_STOPPED_SYSCALL_ENTRY == record.reason:
                        pass
                    elif ASYNC_STOPPED_SYSCALL_RETURN == record.reason:
                        pass
                    elif ASYNC_STOPPED_EXEC == record.reason:
                        pass
                record.stopped_threads = output["stopped-threads"]
                record.core = int(output.get("core"))
                record.fields += ["reason", "stopped_threads", "core"]
        elif record_type == ASYNC_NOTIFY:
            if output_class == ASYNC_NOTIFY_THREAD_GROUP_ADDED:
                record.thread_group_id = output["id"]
                record.fields += ["thread_group_id"]
            elif output_class == ASYNC_NOTIFY_THREAD_GROUP_REMOVED:
                record.thread_group_id = output["id"]
                record.fields += ["thread_group_id"]
            elif output_class == ASYNC_NOTIFY_THREAD_GROUP_STARTED:
                record.thread_group_id = output["id"]
                record.pid = int(output["pid"])
                record.fields += ["thread_group_id", "pid"]
            elif output_class == ASYNC_NOTIFY_THREAD_GROUP_EXITED:
                record.thread_group_id = output["id"]
                record.exit_code = output.get("exit-code")
                record.fields += ["thread_group_id", "exit_code"]
            elif output_class == ASYNC_NOTIFY_THREAD_CREATED:
                record.thread_id = int(output["id"])
                record.thread_group_id = output["group-id"]
                record.fields += ["thread_id", "thread_group_id"]
            elif output_class == ASYNC_NOTIFY_THREAD_EXITED:
                record.thread_id = int(output["id"])
                record.thread_group_id = output["group-id"]
                record.fields += ["thread_id", "thread_group_id"]
            elif output_class == ASYNC_NOTIFY_THREAD_SELECTED:
                record.thread_id = int(output["id"])
                record.fields += ["thread_id"]
            elif output_class == ASYNC_NOTIFY_LIBRARY_LOADED:
                record.library_id = output["id"]
                record.target_name = output["target-name"]
                record.host_name = output["host-name"]
                record.thread_group_id = output.get("thread-group")
                record.fields += ["library_id", "target_name", "host_name",
                                  "thread_group_id"]
            elif output_class == ASYNC_NOTIFY_LIBRARY_UNLOADED:
                record.library_id = output["id"]
                record.target_name = output["target-name"]
                record.host_name = output["host-name"]
                record.thread_group_id = output.get("thread-group")
                record.fields += ["library_id", "target_name", "host_name",
                                  "thread_group_id"]
            elif output_class == ASYNC_NOTIFY_TRACEFRAME_CHANGED:
                if "num" in output:
                    record.end = False
                    record.num = output["num"]
                    record.tracepoint = output["tracepoint"]
                    record.fields += ["end", "num", "tracepoint"]
                else:
                    record.end = True
                    record.fields += ["end"]
            elif output_class == ASYNC_NOTIFY_TSV_CREATED:
                record.name = output["name"]
                record.initial = output["initial"]
                record.fields += ["name", "initial"]
            elif output_class == ASYNC_NOTIFY_TSV_DELETED:
                record.name = output.get("name")
                record.fields += ["name"]
            elif output_class == ASYNC_NOTIFY_TSV_MODIFIED:
                record.name = output["name"]
                record.initial = output["initial"]
                record.current = output.get("current")
                record.fields += ["name", "initial", "current"]
            elif output_class == ASYNC_NOTIFY_BREAKPOINT_CREATED:
                record.breakpoint = GDBMIBreakpoint(output["bkpt"])
                record.fields += ["breakpoint"]
            elif output_class == ASYNC_NOTIFY_BREAKPOINT_MODIFIED:
                record.breakpoint = GDBMIBreakpoint(output["bkpt"])
                record.fields += ["breakpoint"]
            elif output_class == ASYNC_NOTIFY_BREAKPOINT_DELETED:
                record.breakpoint_id = int(output["id"])
                record.fields += ["breakpoint_id"]
            elif output_class == ASYNC_NOTIFY_RECORD_STARTED:
                record.thread_group_id = output["group-id"]
                record.fields += ["thread_group_id"]
            elif output_class == ASYNC_NOTIFY_RECORD_STOPPED:
                record.thread_group_id = output["group-id"]
                record.fields += ["thread_group_id"]
            elif output_class == ASYNC_NOTIFY_CMD_PARAM_CHANGED:
                record.param = output["param"]
                record.value = output["value"]
                record.fields += ["param", "value"]
            elif output_class == ASYNC_NOTIFY_MEMORY_CHANGED:
                record.thread_group_id = output["thread-group"]
                record.addr = output["addr"]
                record.length = output["len"]
                record.mem_type = output.get("type")
                record.fields += ["thread_group_id", "addr", "length", "mem_type"]
        return record

    def pretty_print(self):
        """Return a list of strings (one per line) for pretty-printing."""
        s = ""
        if self.record_type == ASYNC_EXEC:
            if ASYNC_EXEC_STOPPED in self.record_subtypes:
                if self.reason:
                    s = "Thread ID {0} stopped: ".format(self.thread_id)
                    if ASYNC_STOPPED_BREAKPOINT_HIT == self.reason:
                        s += "breakpoint hit"
                    elif ASYNC_STOPPED_WATCHPOINT_TRIGGER == self.reason:
                        s += "watchpoint triggered"
                    elif ASYNC_STOPPED_READ_WATCHPOINT_TRIGGER == self.reason:
                        s += "read watchpoint triggered"
                    elif ASYNC_STOPPED_ACCESS_WATCHPOINT_TRIGGER == self.reason:
                        s += "access watchpoint triggered"
                    elif ASYNC_STOPPED_FUNCTION_FINISHED == self.reason:
                        s += "function finished"
                    elif ASYNC_STOPPED_LOCATION_REACHED == self.reason:
                        s += "location reached"
                    elif ASYNC_STOPPED_WATCHPOINT_SCOPE == self.reason:
                        s += "watchpoint left scope"
                    elif ASYNC_STOPPED_END_STEPPING_RANGE == self.reason:
                        s += "done stepping"
                    elif ASYNC_STOPPED_EXIT_SIGNALLED == self.reason:
                        s += "inferior exited due to signal"
                    elif ASYNC_STOPPED_EXITED == self.reason:
                        s += "inferior exited"
                    elif ASYNC_STOPPED_EXITED_NORMALLY == self.reason:
                        s += "inferior exited normally"
                    elif ASYNC_STOPPED_SIGNAL_RECEIVED == self.reason:
                        s += "signal received"
                    elif ASYNC_STOPPED_SOLIB_EVENT == self.reason:
                        s += "shared library load/unload"
                    elif ASYNC_STOPPED_FORK == self.reason:
                        s += "inferior forked"
                    elif ASYNC_STOPPED_VFORK == self.reason:
                        s += "inferior vforked"
                    elif ASYNC_STOPPED_SYSCALL_ENTRY == self.reason:
                        s += "inferior entered syscall"
                    elif ASYNC_STOPPED_SYSCALL_RETURN == self.reason:
                        s += "inferior returned from syscall"
                    elif ASYNC_STOPPED_EXEC == self.reason:
                        s += "inferior called exec"
                    else:
                        s += "unknown reason {0}".format(self.reason)
                    s = [s] + ["Stopped threads: {0}".format(",".join(self.stopped_threads))]
                else:
                    s = "Thread ID {0} stopped".format(self.thread_id)
            elif ASYNC_EXEC_RUNNING in self.record_subtypes:
                s = "Running, thread ID {0}".format(self.thread_id)
        elif self.record_type == ASYNC_NOTIFY:
            if ASYNC_NOTIFY_THREAD_GROUP_ADDED in self.record_subtypes:
                s = "Thread group {0} added".format(self.thread_group_id)
            elif ASYNC_NOTIFY_THREAD_GROUP_REMOVED in self.record_subtypes:
                s = "Thread group {0} removed".format(self.thread_group_id)
            elif ASYNC_NOTIFY_THREAD_GROUP_STARTED in self.record_subtypes:
                s = "Thread group {0} started, PID = {1}".format(self.thread_group_id,
                                                                 self.pid)
            elif ASYNC_NOTIFY_THREAD_GROUP_EXITED in self.record_subtypes:
                s = "Thread group {0} exited, code = {1}".format(self.thread_group_id,
                                                                 self.exit_code)
            elif ASYNC_NOTIFY_THREAD_CREATED in self.record_subtypes:
                s = "Thread {0} created (group {1})".format(self.thread_id,
                                                            self.thread_group_id)
            elif ASYNC_NOTIFY_THREAD_EXITED in self.record_subtypes:
                s = "Thread {0} exited (group {1})".format(self.thread_id,
                                                           self.thread_group_id)
            elif ASYNC_NOTIFY_THREAD_SELECTED in self.record_subtypes:
                s = "Switched to thread {0}".format(self.thread_id)
            elif ASYNC_NOTIFY_LIBRARY_LOADED in self.record_subtypes:
                s = "Loaded library {0}".format(self.library_id)
                if self.thread_group_id:
                    s += " (group {0})".format(self.thread_group_id)
            elif ASYNC_NOTIFY_LIBRARY_UNLOADED in self.record_subtypes:
                s = "Unloaded library {0}".format(self.library_id)
                if self.thread_group_id:
                    s += " (group {0})".format(self.thread_group_id)
            elif ASYNC_NOTIFY_TRACEFRAME_CHANGED in self.record_subtypes:
                return None
            elif ASYNC_NOTIFY_TSV_CREATED in self.record_subtypes:
                return None
            elif ASYNC_NOTIFY_TSV_DELETED in self.record_subtypes:
                return None
            elif ASYNC_NOTIFY_TSV_MODIFIED in self.record_subtypes:
                return None
            elif ASYNC_NOTIFY_BREAKPOINT_CREATED in self.record_subtypes:
                s = self.breakpoint.pretty_print()
            elif ASYNC_NOTIFY_BREAKPOINT_MODIFIED in self.record_subtypes:
                s = self.breakpoint.pretty_print()
            elif ASYNC_NOTIFY_BREAKPOINT_DELETED in self.record_subtypes:
                s = "Deleted breakpoint {0}".format(self.breakpoint_id)
            elif ASYNC_NOTIFY_RECORD_STARTED in self.record_subtypes:
                s = "Execution log recording started (group {0})".format(self.thread_group_id)
            elif ASYNC_NOTIFY_RECORD_STOPPED in self.record_subtypes:
                s = "Execution log recording stopped (group {0})".format(self.thread_group_id)
            elif ASYNC_NOTIFY_CMD_PARAM_CHANGED in self.record_subtypes:
                s = "{0} is now {1}".format(self.param, self.value)
            elif ASYNC_NOTIFY_MEMORY_CHANGED in self.record_subtypes:
                s = "Memory at {0} (length {1}) written to in group {2}".format(self.addr, self.length, self.thread_group_id)
                if self.mem_type == "code":
                    s += " (this is executable memory)"
        if not isinstance(s, list):
            s = [s]
        if hasattr(self, "frame"):
            s = self.frame.pretty_print() + s
        return s

    def __init__(self):
        """Initialization."""
        super(GDBMIAsyncRecord, self).__init__()

    def __str__(self):
        """Return a basic string representation."""
        return "{0} ASYNC[{1}] {2}\n".format(self.token, self.record_type, self.record_subtypes) + self._str_fields()

class GDBMIStreamRecord(GDBMIRecord):
    """A stream record."""
    string = ""

    @staticmethod
    def create_record(record_type, src):
        """Create a new stream record."""
        record = GDBMIStreamRecord()
        record.record_type = record_type
        record.record_subtypes = set()
        record.token = None
        record.string = src
        record.fields = ["string"]
        return record

    def pretty_print(self):
        """Return a list of strings for pretty-printing by GDBMIPrettyPrinter."""
        # String quotes.
        return self.string[1:-1].split("\\n")

    def __init__(self):
        """Initialization."""
        super(GDBMIStreamRecord, self).__init__()

    def __str__(self):
        """Return a basic string representation."""
        return "{0} STREAM: {1}\n".format(self.token, self.string) + self._str_fields()

class GDBMIResultRecord(GDBMIRecord):
    """A result record."""

    @staticmethod
    def create_record(token, result_class, results):
        """Create a new result record."""
        record = GDBMIResultRecord()
        record.record_type = RESULT
        record.record_subtypes.add(result_class)
        record.token = token
        if result_class == RESULT_CLASS_ERROR:
            record.msg = results[RESULT_MSG]
            if RESULT_CODE in results:
                record.code = results[RESULT_CODE]
            else:
                record.code = None
            record.fields += ["msg", "code"]
        if RESULT_BREAKPOINT in results:
            record.record_subtypes.add(RESULT_BREAKPOINT)
            record.breakpoint = GDBMIBreakpoint(results["bkpt"])
            record.fields += ["breakpoint"]
        if RESULT_BREAKPOINT_TABLE in results:
            record.record_subtypes.add(RESULT_BREAKPOINT_TABLE)
            record.breakpoints = []
            record.fields += ["breakpoints"]
            for bkpt in results[RESULT_BREAKPOINT_TABLE]["body"]:
                record.breakpoints.append(GDBMIBreakpoint(bkpt))
        if RESULT_WATCHPOINT in results:
            record.record_subtypes.add(RESULT_WATCHPOINT)
            record.number = results[RESULT_WATCHPOINT]["number"]
            record.exp = results[RESULT_WATCHPOINT]["exp"]
            record.fields += ["number", "exp"]
        if RESULT_SOURCE_PATH in results:
            record.record_subtypes.add(RESULT_SOURCE_PATH)
            record.source_path = results[RESULT_SOURCE_PATH]
            record.fields += ["source_path"]
        if RESULT_PATH in results:
            record.record_subtypes.add(RESULT_PATH)
            record.path = results[RESULT_PATH]
            record.fields += ["path"]
        if RESULT_CWD in results:
            record.record_subtypes.add(RESULT_CWD)
            record.cwd = results[RESULT_CWD]
            record.fields += ["cwd"]
        if RESULT_THREADS in results:
            record.record_subtypes.add(RESULT_THREADS)
            record.threads = []
            for thread in results[RESULT_THREADS]:
                record.threads.append(GDBMIThread(thread))
            record.fields += ["threads"]
        if RESULT_CURRENT_THREAD in results:
            record.record_subtypes.add(RESULT_CURRENT_THREAD)
            record.current_thread_id = results[RESULT_CURRENT_THREAD]
            record.fields += ["current_thread_id"]
        if RESULT_THREAD_IDS in results:
            record.record_subtypes.add(RESULT_THREAD_IDS)
            record.thread_ids = _make_list(results[RESULT_THREAD_IDS])
            record.fields += ["thread_ids"]
        if RESULT_NUMBER_OF_THREADS in results:
            record.record_subtypes.add(RESULT_NUMBER_OF_THREADS)
            record.num = results[RESULT_NUMBER_OF_THREADS]
            record.fields += ["num"]
        if RESULT_NEW_THREAD_ID in results:
            record.record_subtypes.add(RESULT_NEW_THREAD_ID)
            record.new_thread_id = results[RESULT_NEW_THREAD_ID]
            record.fields += ["new_thread_id"]
        if RESULT_FRAME in results:
            record.record_subtypes.add(RESULT_FRAME)
            record.frame = GDBMIFrame(results[RESULT_FRAME])
            record.fields += ["frame"]
        if RESULT_STACK_DEPTH in results:
            record.record_subtypes.add(RESULT_STACK_DEPTH)
            record.stack_depth = results[RESULT_STACK_DEPTH]
            record.fields += ["stack_depth"]
        if RESULT_STACK_ARGS in results:
            record.record_subtypes.add(RESULT_STACK_ARGS)
            record.arguments = [[]] * len(results[RESULT_STACK_ARGS])
            for frame in results[RESULT_STACK_ARGS]:
                level = int(frame["level"])
                for arg_name in frame["args"]["name"]:
                    record.arguments[level].append(arg_name)
            record.fields += ["arguments"]
        if RESULT_STACK in results:
            record.record_subtypes.add(RESULT_STACK)
            if isinstance(results[RESULT_STACK]["frame"], list):
                record.stack = [[]] * len(results[RESULT_STACK]["frame"])
                for frame in results[RESULT_STACK]["frame"]:
                    level = int(frame["level"])
                    record.stack[level] = GDBMIFrame(frame)
            else:
                record.stack = [GDBMIFrame(results[RESULT_STACK]["frame"])]
            record.fields += ["stack"]
            record.record_subtypes.add(len(record.stack))
        if RESULT_LOCALS in results:
            record.record_subtypes.add(RESULT_LOCALS)
            record.local_variables = {}
            for local in results[RESULT_LOCALS]:
                if "value" in local:
                    record.local_variables[local["name"]] = local["value"]
                else:
                    record.local_variables[local["name"]] = None
            record.fields += ["local_variables"]
        if RESULT_VARIABLES in results:
            record.record_subtypes.add(RESULT_VARIABLES)
            record.variables = {}
            for var in results[RESULT_VARIABLES]:
                if "value" in var:
                    record.variables[var["name"]] = var["value"]
                else:
                    record.variables[var["name"]] = None
            record.fields += ["variables"]
        if RESULT_ASM in results:
            record.record_subtypes.add(RESULT_ASM)
            # TODO.
        if RESULT_VALUE in results:
            record.record_subtypes.add(RESULT_VALUE)
            record.value = results[RESULT_VALUE]
            record.fields += ["value"]
        if RESULT_CHANGED_REGISTERS in results:
            record.record_subtypes.add(RESULT_CHANGED_REGISTERS)
            record.changed_registers = _make_list(results[RESULT_CHANGED_REGISTERS])
            record.fields += ["changed_registers"]
        if RESULT_REGISTER_NAMES in results:
            record.record_subtypes.add(RESULT_REGISTER_NAMES)
            record.register_names = _make_list(results[RESULT_CHANGED_REGISTERS])
            record.fields += ["register_names"]
        if RESULT_REGISTER_VALUES in results:
            record.record_subtypes.add(RESULT_REGISTER_VALUES)
            record.register_values = {}
            for reg in results[RESULT_REGISTER_VALUES]:
                record.register_values[reg["number"]] = reg["value"]
            record.fields += ["register_values"]
        if RESULT_MEMORY in results:
            record.record_subtypes.add(RESULT_MEMORY)
            record.begin = results[RESULT_MEMORY]["begin"]
            record.offset = results[RESULT_MEMORY]["offset"]
            record.end = results[RESULT_MEMORY]["end"]
            record.contents = results[RESULT_MEMORY]["contents"]
            record.fields += ["begin", "offset", "end", "contents"]
        if RESULT_TRACE_VARIABLES in results:
            record.record_subtypes.add(RESULT_TRACE_VARIABLES)
            # TODO.
        if RESULT_LINES in results:
            record.record_subtypes.add(RESULT_LINES)
            record.lines = {}
            for line in results[RESULT_LINES]:
                record.lines[line["pc"]] = line["line"]
            record.fields += ["lines"]
        if RESULT_FILES in results:
            record.record_subtypes.add(RESULT_FILES)
            record.files = []
            for f in results[RESULT_FILES]:
                record.files.append(f["file"])
            record.fields += ["files"]
        if RESULT_LINE in results:
            record.record_subtypes.add(RESULT_LINE)
            record.line = results[RESULT_LINE]
            record.fields += ["line"]
        if RESULT_FILE in results:
            record.record_subtypes.add(RESULT_FILE)
            record.file = results[RESULT_FILE]
            record.fields += ["file"]
        if RESULT_FULLNAME in results:
            record.record_subtypes.add(RESULT_FULLNAME)
            record.fullname = results[RESULT_FULLNAME]
            record.fields += ["fullname"]
        if RESULT_MACRO_INFO in results:
            record.record_subtypes.add(RESULT_MACRO_INFO)
            record.macro_info = results[RESULT_MACRO_INFO]
            record.fields += ["macro_info"]
        if RESULT_RESULT in results:
            record.record_subtypes.add(RESULT_RESULT)
            record.result = results[RESULT_RESULT]
            record.fields += ["result"]
        if RESULT_GROUPS in results:
            record.record_subtypes.add(RECORD_GROUPS)
            # TODO.
        if RESULT_OS_DATA_TABLE in results:
            record.record_subtypes.add(RESULT_OS_DATA_TABLE)
            # TODO.
        if RESULT_THREAD_GROUP in results:
            record.record_subtypes.add(RESULT_THREAD_GROUP)
            record.thread_group_id = results[RESULT_THREAD_GROUP]
            record.fields += ["thread_group_id"]
        if RESULT_INFERIOR_TTY in results:
            record.record_subtypes.add(RESULT_INFERIOR_TTY)
            record.inferior_tty = results[RESULT_INFERIOR_TTY]
            record.fields += ["inferior_tty"]
        if RESULT_TIME in results:
            record.record_subtypes.add(RESULT_TIME)
            record.wallclock = results[RESULT_TIME]["wallclock"]
            record.user = results[RESULT_TIME]["user"]
            record.system = results[RESULT_TIME]["system"]
            record.fields += ["wallclock", "user", "system"]
        return record

    def pretty_print(self):
        """Return a list of strings for pretty-printing by GDBMIPrettyPrinter."""
        s = []
        if set([RESULT_CLASS_DONE]) == self.record_subtypes:
            s += ["Done"]
        if set([RESULT_CLASS_EXIT]) == self.record_subtypes:
            s += ["Exit"]
        if set([RESULT_CLASS_RUNNING]) == self.record_subtypes:
            s += ["Running"]
        if set([RESULT_CLASS_ERROR]) == self.record_subtypes:
            if self.code:
                s += ["Error {0}: {1}".format(self.code, self.msg)]
            else:
                s += ["Error: {0}".format(self.msg)]
        if RESULT_BREAKPOINT in self.record_subtypes:
            s += self.breakpoint.pretty_print()
        if RESULT_BREAKPOINT_TABLE in self.record_subtypes:
            for breakpoint in self.breakpoints:
                s += breakpoint.pretty_print()
        if RESULT_WATCHPOINT in self.record_subtypes:
            s += ["Watchpoing {0} for {1}".format(self.number, self.exp)]
        if RESULT_SOURCE_PATH in self.record_subtypes:
            s += ["Source search path: " + self.source_path]
        if RESULT_PATH in self.record_subtypes:
            s += ["Executable and object file path: " + self.path]
        if RESULT_CWD in self.record_subtypes:
            s += ["Working directory: " + self.cwd]
        if RESULT_THREADS in self.record_subtypes:
            s += self.threads[0].pretty_print()
            for thread in self.threads[1:]:
                s += thread.pretty_print(return_header = False)
        if RESULT_CURRENT_THREAD in self.record_subtypes:
            s += ["Current thread ID: {0}".format(self.current_thread_id)]
        if RESULT_THREAD_IDS in self.record_subtypes:
            s += [", ".join(self.thread_ids)]
        if RESULT_NUMBER_OF_THREADS in self.record_subtypes:
            s += ["{0} threads total".format(self.num)]
        if RESULT_NEW_THREAD_ID in self.record_subtypes:
            s += ["New thread ID: {0}".format(self.new_thread_id)]
        if RESULT_STACK_DEPTH in self.record_subtypes:
            s += ["Stack depth: {0}".format(self.stack_depth)]
        if RESULT_STACK_ARGS in self.record_subtypes:
            for level, names in enumerate(self.arguments):
                s += ["[{0}] {1}".format(level, ", ".join(names))]
        if RESULT_STACK in self.record_subtypes:
            for frame in self.stack:
                s += frame.pretty_print()
        if RESULT_LOCALS in self.record_subtypes:
            if not self.local_variables:
                s += ["No locals"]
            for var in self.local_variables:
                if self.local_variables[var] is not None:
                    s += ["{0} = {1}".format(var, self.local_variables[var])]
                else:
                    s += ["{0}".format(var)]
        if RESULT_VARIABLES in self.record_subtypes:
            if not self.variables:
                s += ["No variables"]
            for var in self.variables:
                if self.variables[var] is not None:
                    s += ["{0} = {1}".format(var, self.variables[var])]
                else:
                    s += ["{0}".format(var)]
        if RESULT_ASM in self.record_subtypes:
            pass
        if RESULT_VALUE in self.record_subtypes:
            s += ["{0}".format(self.value)]
        if RESULT_CHANGED_REGISTERS in self.record_subtypes:
            s += ["Changed registers: {0}".format(", ".join(self.changed_registers))]
        if RESULT_REGISTER_NAMES in self.record_subtypes:
            s += ["Register names: {0}".format(", ".join(self.register_names))]
        if RESULT_REGISTER_VALUES in self.record_subtypes:
            for reg in self.register_values:
                s += ["{0:<6}{1}".format(reg, self.register_values[reg])]
        if RESULT_MEMORY in self.record_subtypes:
            pass
        if RESULT_TRACE_VARIABLES in self.record_subtypes:
            pass
        if RESULT_LINES in self.record_subtypes:
            for pc in self.lines:
                s += ["{0:<16}{1}".format(pc, self.lines[pc])]
        if RESULT_FILES in self.record_subtypes:
            s += ["Source files:"]
            for f in self.files:
                s += ["    {0}".format(f)]
        if RESULT_LINE in self.record_subtypes:
            if isinstance(self.line, list):
                for line in self.line:
                    s += ["Line number: {0}".format(line)]
            else:
                s += ["Line number: {0}".format(self.line)]
        if RESULT_FILE in self.record_subtypes:
            if isinstance(self.file, list):
                for f in self.file:
                    s += ["Current source file: {0}".format(f)]
            else:
                s += ["Current source file: {0}".format(self.file)]
        if RESULT_FULLNAME in self.record_subtypes:
            s += ["Current source file location: {0}".format(self.fullname)]
        if RESULT_MACRO_INFO in self.record_subtypes:
            if self.macro_info == "0":
                s += ["Does not include preprocessor macro info"]
            elif self.macro_info == "1":
                s += ["Includes preprocessor macro info"]
            else:
                s += ["Macro info: {0}".format(self.macro_info)]
        if RESULT_RESULT in self.record_subtypes:
            s += ["Supported features: {0}".format(", ".join(self.result))]
        if RESULT_GROUPS in self.record_subtypes:
            pass
        if RESULT_OS_DATA_TABLE in self.record_subtypes:
            pass
        if RESULT_THREAD_GROUP in self.record_subtypes:
            s += ["Thread group ID: {0}".format(self.thread_group_id)]
        if RESULT_INFERIOR_TTY in self.record_subtypes:
            s += ["Inferior TTY: {0}".format(self.inferior_tty)]
        if RESULT_FRAME in self.record_subtypes:
            s += self.frame.pretty_print()
        if RESULT_TIME in self.record_subtypes:
            s += ["Wallclock: {0}, user: {1}, system: {2}".format(self.wallclock,
                                                                  self.user,
                                                                  self.system)]
        if not s:
            return None
        return s

    def __init__(self):
        """Initialization."""
        super(GDBMIResultRecord, self).__init__()

    def __str__(self):
        """Return a basic string representation."""
        return "{0} RESULT[{1}]: {2}\n".format(self.token, self.record_type, self.record_subtypes) + self._str_fields()

class GDBMIUnknownRecord(GDBMIRecord):
    """Some other type of record."""

    @staticmethod
    def create_record(line):
        """Create a new record of unknown type."""
        record = GDBMIUnknownRecord()
        record.output = line

    def __init__(self):
        """Initialization."""
        super(GDBMIUnknownRecord, self).__init__()
        self.record_type = UNKNOWN
        self.fields = ["output"]

    def __str__(self):
        """Return a basic string representation."""
        return "{0} UNKNOWN: {1}".format(self.token, self.output)

class GDBMIFrame:
    """A stack frame."""

    def __init__(self, frame):
        """Initialize the frame from output data."""
        self.level = frame.get("level")
        self.addr = frame.get("addr")
        self.func = frame.get("func")
        self.source_file = frame.get("file")
        self.fullname = frame.get("fullname")
        self.line = frame.get("line")
        self.binary_file = frame.get("from")
        if "args" in frame:
            self.args = {}
            for arg in frame["args"]:
                self.args[arg["name"]] = arg.get("value", "")
        else:
            self.args = None

    def pretty_print(self):
        """Pretty-printing interface for GDBMIPrettyPrinter."""
        s = ""
        if self.level is not None:
            s += "#{0:<5}".format(self.level)
        s += str(self.addr)
        if self.func:
            s += " in {0}(".format(self.func)
            if self.args:
                for k in self.args:
                    s += "{0}={1}, ".format(k, self.args[k])
                s = s[:-2] # Remove trailing ", ".
            s += ")"
        if self.fullname:
            s += " from {0}".format(self.fullname)
            if self.line is not None:
                s += ":{0}".format(self.line)
        return [s]

    def __str__(self):
        """Return a basic string representation."""
        return "GDBMIFrame: level = {0}, addr = {1}, func = {2}, fullname = {3}, line = {4}, args = {5}".format(self.level, self.addr, self.func, self.fullname, self.line, self.args)

    def __key(self):
        return (self.level, self.addr, self.func, self.source_file,
                self.line, self.binary_file)

    def __eq__(self, other):
        return self.__key() == other.__key()

    def __hash__(self):
        return hash(self.__key())

class GDBMIBreakpoint:
    """A breakpoint."""

    def __init__(self, bkpt):
        self.number = bkpt["number"]
        self.breakpoint_type = bkpt["type"]
        self.catch_type = bkpt.get("catch-type")
        self.disposition = bkpt["disp"]
        self.enabled = bkpt["enabled"]
        self.addr = bkpt.get("addr")
        self.func = bkpt.get("func")
        self.filename = bkpt.get("filename")
        self.fullname = bkpt.get("fullname")
        self.line = bkpt.get("line")
        self.at = bkpt.get("at")
        self.pending = bkpt.get("pending")
        self.evaluated_by = bkpt.get("evaluated-by")
        self.thread = bkpt.get("thread")
        self.task = bkpt.get("task")
        self.cond = bkpt.get("cond")
        self.ignore = bkpt.get("ignore")
        self.enable = bkpt.get("enable")
        self.timeframe_usage = bkpt.get("timeframe-usage")
        self.static_tracepoint_marker_string_id = bkpt.get("static-tracepoint-marker-string-id")
        self.mask = bkpt.get("mask")
        self.pass_count = bkpt.get("pass")
        self.original_location = bkpt.get("original-location")
        self.times = bkpt.get("times")
        self.installed = bkpt.get("installed")
        self.what = bkpt.get("what")
        self.thread_groups = bkpt.get("thread-groups")

    def pretty_print(self):
        """Pretty-printing interface for GDBMIPrettyPrinter."""
        return []

    def __str__(self):
        """Return a basic string representation."""
        return "GDBMIBreakpoint: no = {0}, type = {1}, enabled = {2}, addr = {3}, func = {4}, fullname = {5}, line = {6}, at = {7}".format(self.number, self.breakpoint_type, self.enabled, self.addr, self.func, self.fullname, self.line, self.at)

    def __key(self):
        return (self.number,
                self.breakpoint_type,
                self.catch_type,
                self.disposition,
                self.enabled,
                self.addr,
                self.func,
                self.filename,
                self.fullname,
                self.line,
                self.at,
                self.pending,
                self.evaluated_by,
                self.thread,
                self.task,
                self.cond,
                self.ignore,
                self.enable,
                self.timeframe_usage,
                self.static_tracepoint_marker_string_id,
                self.mask,
                self.pass_count,
                self.original_location,
                self.times,
                self.installed,
                self.what,
                self.thread_groups)

    def __eq__(self, other):
        return self.__key() == other.__key()

    def __hash__(self):
        return hash(self.__key())

class GDBMIThread:
    """A thread."""

    def __init__(self, thread):
        self.thread_id = int(thread["id"])
        self.target_id = thread["target-id"]
        self.details = thread.get("details")
        self.name = thread.get("name")
        self.state = thread["state"]
        self.current = thread.get("current")
        self.core = thread.get("core")
        self.frame = thread.get("frame")
        if self.frame:
            self.frame = GDBMIFrame(self.frame)

    def pretty_print(self, return_header = True):
        """Pretty-printing interface for GDBMIPrettyPrinter."""
        fmt = "{0:<5}{1:<48}{2:<11}{3:<7}{4:<5}"
        header = "  " + fmt.format("ID", "Target ID", "State", "Core", "Frame")
        core = "?"
        frame = "?"
        if self.core is not None:
            core = self.core
        if self.frame:
            # Should only be one line.
            frame = self.frame.pretty_print()[0]
        line = fmt.format(self.thread_id, self.target_id, self.state,
                          core, frame)
        if self.current:
            line = "* " + line
        else:
            line = "  " + line
        if return_header:
            return [header, line]
        else:
            return [line]

    def __str__(self):
        """Return a basic string representation."""
        return "GDBMIThread: id = {0}, target = {1}, state = {2}, frame = {3}".format(self.thread_id, self.target_id, self.state, self.frame)

    def __key(self):
        return (self.thread_id, self.target_id, self.details, self.name,
                self.state, self.current, self.core)

    def __eq__(self, other):
        return self.__key() == other.__key()

    def __hash__(self):
        return hash(self.__key())
