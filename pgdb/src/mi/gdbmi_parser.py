"""Parses GDB Machine Interface output into Python structures."""

import re

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

class GDBMIParser:
    """Parse output from GDB into an AST."""

    _term = "(gdb)" # The terminator symbol
    _result_record_symbol = "^"
    _async_record_symbols = ["*", "+", "="]
    _stream_record_symbols = ["~", "@", "&"]
    _all_record_symbols = [_result_record_symbol] + _async_record_symbols + _stream_record_symbols
    _result_class = {"done": RESULT_CLASS_DONE,
                     "running": RESULT_CLASS_RUNNING,
                     "connected": RESULT_CLASS_CONNECTED,
                     "error": RESULT_CLASS_ERROR,
                     "exit": RESULT_CLASS_EXIT}
    _oob_mapper = {"*": ASYNC_EXEC,
                   "+": ASYNC_STATUS,
                   "=": ASYNC_NOTIFY,
                   "~": STREAM_CONSOLE,
                   "@": STREAM_TARGET,
                   "&": STREAM_LOG}

    def __init__(self):
        """Set up the parser."""
        self.output_re = re.compile(r"([0-9]*)(" + "|".join(["\\" + item for item in self._all_record_symbols]) + ")(.*)")
        self.result_re = re.compile(r"(" + "|".join(self._result_class.keys()) + ")(.*)")
        self.async_re = re.compile(r"([a-zA-Z0-9_\-]*)(\,.*)?")
        self._value_parsers = {'{': self.parse_tuple,
                               '[': self.parse_list,
                               '"': self.parse_const}

    def parse_output(self, src):
        """Take a set of output from GDB and parse it into an AST.

        Returns a list of records.

        """
        lines = src.split("\n")
        records = []
        for line in lines:
            line = line.strip()
            # Check for the terminator.
            if line == self._term:
                continue
            else:
                parts = self.output_re.match(line)
                if not parts:
                    record = GDBMIRecord()
                    record.record_type = UNKNOWN
                    record.output = line
                    records.append(record)
                    continue
                token, symbol, rest = parts.groups()
                if not token:
                    token = None
                else:
                    token = int(token)
                if symbol == self._result_record_symbol:
                    records.append(self.parse_result_record(token, rest))
                else:
                    records.append(self.parse_oob_record(token, symbol, rest))
        return records

    def parse_result_record(self, token, src):
        """Parse a result record into a GDBMIResultRecord()."""
        parts = self.result_re.match(src)
        if not parts:
            raise ValueError(src)
        result_class, results = parts.groups()
        if not result_class:
            raise ValueError(src)
        return GDBMIResultRecord.create_record(token,
                                               self._result_class[result_class],
                                               self.parse_result_list(results[1:]))

    def parse_oob_record(self, token, symbol, src):
        """Parse an out-of-band record, either an async record or a stream record."""
        if symbol in self._async_record_symbols:
            return self.parse_async_record(token, symbol, src)
        else:
            # Stream records do not have tokens.
            return self.parse_stream_record(symbol, src)

    def parse_async_record(self, token, symbol, src):
        """Parse an exec, status, or notify async record into a GDBMIAsyncRecord."""
        output_class, output = self.parse_async_output(src)
        return GDBMIAsyncRecord.create_record(self._oob_mapper[symbol],
                                                token,
                                                output_class,
                                                output)

    def parse_stream_record(self, symbol, src):
        """Parse a console, target, or log stream record into a GDBMIStreamRecord."""
        return GDBMIStreamRecord.create_record(self._oob_mapper[symbol], src)

    def parse_async_output(self, src):
        """Parse the output of an async record.
        Returns a tuple of the async class and a dict of results."""
        match = self.async_re.match(src)
        if not match:
            raise ValueError(src)
        async_class, rest = match.groups()
        if rest:
            # Remove first comma.
            rest = rest[1:]
            if rest == "end":
                # Hack to catch the =traceframe-changed,end record.
                return async_class, {}
            return async_class, self.parse_result_list(rest)
        else:
            return async_class, {}

    def parse_result(self, src):
        """Parse a result into a (variable, value) tuple."""
        variable, equal, value = src.partition("=")
        return variable, self.parse_value(value)

    def parse_value(self, src):
        """Parse a value, either a tuple, a list, or a constant."""
        if src[0] in self._value_parsers:
            return self._value_parsers[src[0]](src)
        else:
            # There is a legacy format, key=value. Not supported.
            raise ValueError(src)

    def parse_tuple(self, src):
        """Parse a tuple into a dict of results."""
        if src == "{}":
            # Empty tuple.
            return {}
        return self.parse_result_list(src[1:-1])

    def parse_list(self, src):
        """Parse a list into either a list of values, or a dict of results."""
        if src == "[]":
            return []
        src = src[1:-1]
        brackets = 0
        in_quote = False
        end = 0
        start = 0
        prev_char = ""
        results = []
        # The structure of this is similar to parse_result_list.
        # But we may have a list of values instead, so we need to identify that.
        for char in src:
            if (char == "{" or char == "[") and not in_quote:
                brackets += 1
            elif (char == "}" or char == "]") and not in_quote:
                brackets -= 1
            elif char == '"' and prev_char != "\\":
                in_quote = not in_quote
            elif char == "=" and brackets == 0 and not in_quote:
                # We have a list of results, so use that logic instead.
                return self.parse_result_list(src)
            elif char == "," and brackets == 0 and not in_quote:
                # Found end of entry.
                results.append(self.parse_value(src[start:end]))
                start = end + 1
            end += 1
            prev_char = char
        # Parse the last value, if needed.
        if src[start:end]:
            results.append(self.parse_value(src[start:end]))
        return results

    def parse_const(self, src):
        """Parse a constant and return its value."""
        # Just remove the quotes.
        return src[1:-1]

    def parse_result_list(self, src):
        """Parse a result list into a dict of results."""
        length = 0
        brackets = 0
        in_quote = False
        results = {}
        variable_counts = {}
        variable = None
        right = ""
        prev_char = ""
        while True:
            (variable, sep, right) = src.partition("=")
            if not sep:
                break
            # Seek forward until we find the end of the value.
            # Account for nested lists and tuples.
            for char in right:
                if (char == "{" or char == "[") and not in_quote:
                    brackets += 1
                elif (char == "}" or char == "]") and not in_quote:
                    brackets -= 1
                elif char == '"' and prev_char != "\\":
                    # Ignore the \" escape sequence.
                    in_quote = not in_quote
                elif char == "," and brackets == 0 and not in_quote:
                    # Found the end of the value.
                    value = self.parse_value(right[:length])
                    # Add it to the results dict.
                    if variable in variable_counts:
                        if variable_counts[variable] == 1:
                            # Convert entry to list.
                            results[variable] = [results[variable], value]
                        else:
                            results[variable].append(value)
                        variable_counts[variable] += 1
                    else:
                        results[variable] = value
                        variable_counts[variable] = 1
                    src = right[length + 1:]
                    length = 0
                    break
                length += 1
                prev_char = char
            if length >= len(right):
                break
        # Parse last entry.
        if variable and right:
            value = self.parse_value(right)
            if variable in variable_counts:
                if variable_counts[variable] == 1:
                    results[variable] = [results[variable], value]
                else:
                    results[variable].append(value)
            else:
                results[variable] = value
        return results

def _make_list(item):
    """Make item into a list if it is not."""
    if type(item) is list:
        return item
    return [item]

class GDBMIRecord:
    """The top-level GDB record class."""
    record_type = None
    record_subtypes = set()
    token = None
    fields = []

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
        else:
            record.frame = None
        record.fields += ["frame"]
        if record_type == ASYNC_EXEC:
            record.thread_id = output["thread-id"]
            record.fields += ["thread-id"]
            if output_class == ASYNC_EXEC_STOPPED:
                record.reason = output["reason"]
                record.stopped_threads = output["stopped-threads"]
                record.core = output.get("core")
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
                record.pid = output["pid"]
                record.fields += ["thread_group_id", "pid"]
            elif output_class == ASYNC_NOTIFY_THREAD_GROUP_EXITED:
                record.thread_group_id = output["id"]
                record.exit_code = output.get("exit-code")
                record.fields += ["thread_group_id", "exit_code"]
            elif output_class == ASYNC_NOTIFY_THREAD_CREATED:
                record.thread_id = output["id"]
                record.thread_group_id = output["group-id"]
                record.fields += ["thread_id", "thread_group_id"]
            elif output_class == ASYNC_NOTIFY_THREAD_EXITED:
                record.thread_id = output["id"]
                record.thread_group_id = output["group-id"]
                record.fields += ["thread_id", "thread_group_id"]
            elif output_class == ASYNC_NOTIFY_THREAD_SELECTED:
                record.thread_id = output["id"]
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
                record.breakpoint_id = output["id"]
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

    def __str__(self):
        return "{0} ASYNC[{1}] {2}".format(self.token, self.record_type, self.record_subtypes)

class GDBMIStreamRecord(GDBMIRecord):
    """A stream record."""
    string = ""

    @staticmethod
    def create_record(record_type, src):
        record = GDBMIStreamRecord()
        record.record_type = record_type
        record.record_subtypes = set()
        record.token = None
        record.string = src
        record.fields = ["string"]
        return record

    def __str__(self):
        return "{0} STREAM: {1}".format(self.token, self.string)

class GDBMIResultRecord(GDBMIRecord):
    """A result record."""

    @staticmethod
    def create_record(token, result_class, results):
        record = GDBMIResultRecord()
        record.record_type = RESULT
        record.record_subtypes.add(result_class)
        record.token = token
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
            record.threads = _make_list(results[RESULT_THREADS])
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
            record.fields += ["arguemtns"]
        if RESULT_STACK in results:
            record.record_subtypes.add(RESULT_STACK)
            record.stack = [[]] * len(results[RESULT_STACK])
            for frame in results[RESULT_STACK]:
                level = int(frame["level"])
                record.stack[level] = GDBMIFrame(frame)
            record.fields += ["stack"]
        if RESULT_LOCALS in results:
            record.record_subtypes.add(RESULT_LOCALS)
            record.local_variables = {}
            for local in results[RESULT_LOCALS]:
                record.local_variables[local["name"]] = local["value"]
            record.fields += ["local_variables"]
        if RESULT_VARIABLES in results:
            record.record_subtypes.add(RESULT_VARIABLES)
            record.variables = {}
            for var in results[RESULT_VARIABLES]:
                record.variables[var["name"]] = var["value"]
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

    def __str__(self):
        return "{0} RESULT[{1}]: {2}".format(self.token, self.record_type, self.record_subtypes)

class GDBMIUnknownRecord(GDBMIRecord):
    """Some other type of record."""
    output = None

    def __str__(self):
        return "{0} UNKNOWN: {1}".format(self.token, self.output)

class GDBMIFrame:
    """A stack frame."""

    def __init__(self, frame):
        if not frame:
            # Fill with dummy values.
            frame = {"level": None,
                     "addr": None}
        self.level = frame["level"]
        self.addr = frame["addr"]
        self.func = frame.get("func")
        self.source_file = frame.get("file")
        self.line = frame.get("line")
        self.binary_file = frame.get("from")

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
        if not bkpt:
            # Fill with dummy values.
            bkpt = {"number": None,
                    "type": None,
                    "disp": None,
                    "enabled": None}
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
        if not thread:
            # Fill with dummy values.
            thread = {"id": None,
                      "target-id": None,
                      "state": None}
        self.thread_id = thread["id"]
        self.target_id = thread["target-id"]
        self.details = thread.get("details")
        self.name = thread.get("name")
        self.state = thread["state"]
        self.current = thread.get("current")
        self.core = thread.get("core")

    def __key(self):
        return (self.thread_id, self.target_id, self.details, self.name,
                self.state, self.current, self.core)

    def __eq__(self, other):
        return self.__key() == other.__key()

    def __hash__(self):
        return hash(self.__key())
