"""Parses GDB Machine Interface output into Python structures."""

import re

RESULT_CLASS_DONE = "DONE"
RESULT_CLASS_RUNNING = "RUNNING"
RESULT_CLASS_CONNECTED = "CONNECTED"
RESULT_CLASS_ERROR = "ERROR"
RESULT_CLASS_EXIT = "EXIT"
RESULT = "RESULT"
ASYNC_EXEC = "EXEC"
ASYNC_STATUS = "STATUS"
ASYNC_NOTIFY = "NOTIFY"
STREAM_CONSOLE = "CONSOLE"
STREAM_TARGET = "TARGET"
STREAM_LOG = "LOG"
TERMINATOR = "TERM"
UNKNOWN = "UNKNOWN"

# Todo: We do not support escape sequences in constants.

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

    def parse_output(self, src):
        """Take a set of output from GDB and parse it into an AST.
        Returns a tuple, the first element being a list of out-of-band records,
        and the second element a list of result records."""
        lines = src.split("\n")
        records = []
        oob_records = []
        result_records = []
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
                    oob_records.append(record)
                    continue
                (token, symbol, rest) = parts.groups()
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
        (result_class, results) = parts.groups()
        if not result_class:
            raise ValueError(src)
        result_record = GDBMIResultRecord()
        result_record.record_type = RESULT
        result_record.token = token
        result_record.result_class = self._result_class[result_class]
        result_record.results = self.parse_result_list(results[1:])
        return result_record

    def parse_oob_record(self, token, symbol, src):
        """Parse an out-of-band record, either an async record or a stream record."""
        if symbol in self._async_record_symbols:
            return self.parse_async_record(token, symbol, src)
        else:
            # Stream records do not have tokens.
            return self.parse_stream_record(symbol, src)

    def parse_async_record(self, token, symbol, src):
        """Parse an exec, status, or notify async record into a GDBMIAsyncRecord."""
        record_type = self._oob_mapper[symbol]
        (output_class, output) = self.parse_async_output(src)
        record = GDBMIAsyncRecord()
        record.record_type = self._oob_mapper[symbol]
        record.token = token
        record.output_class = output_class
        record.output = output
        return record

    def parse_stream_record(self, symbol, src):
        """Parse a console, target, or log stream record into a GDBMIStreamRecord."""
        record = GDBMIStreamRecord()
        record.record_type = self._oob_mapper[symbol]
        record.string = src
        return record

    def parse_async_output(self, src):
        """Parse the output of an async record.
        Returns a tuple of the async class and a dict of results."""
        match = self.async_re.match(src)
        if not match:
            raise ValueError(src)
        (async_class, rest) = match.groups()
        if rest:
            # Remove first comma.
            return (async_class, self.parse_result_list(rest[1:]))
        else:
            return (async_class, {})

    def parse_result(self, src):
        """Parse a result into a (variable, value) tuple."""
        (variable, equal, value) = src.partition("=")
        return (variable, self.parse_value(value))

    def parse_value(self, src):
        """Parse a value, either a tuple, a list, or a constant."""
        value_parsers = {'{': self.parse_tuple,
                         '[': self.parse_list,
                         '"': self.parse_const}
        if src[0] in value_parsers:
            return value_parsers[src[0]](src)
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
        """Parse a list into either a list of values, or a list or results."""
        if src == "[]":
            return []
        src = src[1:-1]
        brackets = 0
        end = 0
        start = 0
        results = []
        result = False
        for char in src:
            if char == "{" or char == "[":
                brackets += 1
            elif char == "}" or char == "]":
                brackets -= 1
            elif char == "=" and brackets == 0:
                result = True
            elif char == "," and brackets == 0:
                # Found end of entry.
                if result:
                    results.append(self.parse_result(src[start:end]))
                else:
                    results.append(self.parse_value(src[start:end]))
                start = end + 1
            end += 1
        # Parse the last value, if needed.
        if src[start:end]:
            if result:
                results.append(self.parse_result(src[start:end]))
            else:
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
        variable = None
        right = ""
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
                elif char == '"':
                    # Todo: This does not handle escape sequences.
                    in_quote = not in_quote
                elif char == "," and brackets == 0 and not in_quote:
                    # Found the end of the value.
                    value = self.parse_value(right[:length])
                    results[variable] = value
                    src = right[length + 1:]
                    length = 0
                    break
                length += 1
            if length >= len(right):
                break
        # Parse last entry.
        if variable and right:
            results[variable] = self.parse_value(right)
        return results

class GDBMIRecord:
    """The top-level GDB record class."""
    record_type = None
    token = None

class GDBMIAsyncRecord(GDBMIRecord):
    """An async record."""
    output_class = None
    output = None

    def __str__(self):
        return "{0} ASYNC[{1}]: {2}".format(self.token, self.output_class, self.output)

class GDBMIStreamRecord(GDBMIRecord):
    """A stream record."""
    string = ""

    def __str__(self):
        return "{0} STREAM: {1}".format(self.token, self.string)

class GDBMIResultRecord(GDBMIRecord):
    """A result record."""
    result_class = None
    results = {}

    def __str__(self):
        return "{0} RESULT[{1}]: {2}".format(self.token, self.result_class, self.results)

class GFBMIUnknownRecord(GDBMIRecord):
    """Some other type of record."""
    output = None

    def __str__(self):
        return "{0} UNKNOWN: {1}".format(self.token, self.output)

