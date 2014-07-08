"""Parses GDB Machine Interface output into Python structures."""

import re
from gdbmi_records import (RESULT_CLASS_DONE, RESULT_CLASS_RUNNING,
                           RESULT_CLASS_CONNECTED, RESULT_CLASS_ERROR,
                           RESULT_CLASS_EXIT, ASYNC_EXEC, ASYNC_STATUS,
                           ASYNC_NOTIFY, STREAM_CONSOLE, STREAM_TARGET,
                           STREAM_LOG, GDBMIAsyncRecord, GDBMIStreamRecord,
                           GDBMIResultRecord, GDBMIUnknownRecord)

class GDBMIParser:
    """Parse output from GDB into an AST."""

    _term = "(gdb)" # The terminator symbol
    _result_record_symbol = "^"
    _async_record_symbols = ["*", "+", "="]
    _stream_record_symbols = ["~", "@", "&"]
    _all_record_symbols = ([_result_record_symbol] + _async_record_symbols +
                           _stream_record_symbols)
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
        self.output_re = re.compile(r"([0-9]*)(" + "|".join(
            ["\\" + item for item in self._all_record_symbols]) + ")(.*)")
        self.result_re = re.compile(r"(" + "|".join(
            self._result_class.keys()) + ")(.*)")
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
                    records.append(GDBMIUnknownRecord.create_record(line))
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
        return GDBMIResultRecord.create_record(
            token,
            self._result_class[result_class],
            self.parse_result_list(results[1:]))

    def parse_oob_record(self, token, symbol, src):
        """Parse an out-of-band record, either an async or a stream record."""
        if symbol in self._async_record_symbols:
            return self.parse_async_record(token, symbol, src)
        else:
            # Stream records do not have tokens.
            return self.parse_stream_record(symbol, src)

    def parse_async_record(self, token, symbol, src):
        """Parse an exec, status, or notify async record."""
        output_class, output = self.parse_async_output(src)
        return GDBMIAsyncRecord.create_record(self._oob_mapper[symbol],
                                              token,
                                              output_class,
                                              output)

    def parse_stream_record(self, symbol, src):
        """Parse a console, target, or log stream record."""
        return GDBMIStreamRecord.create_record(self._oob_mapper[symbol], src)

    def parse_async_output(self, src):
        """Parse the output of an async record.

        Returns a tuple of the async class and a dict of results.

        """
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
