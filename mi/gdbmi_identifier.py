"""A means to nicely identify aspects of GDBMI records."""

from gdbmi_parser import *

class GDBMIRecordIdentifier:
    """Identify input GDBMI records.

    This should be used by calling identify on the record. It will return a list that contains
    the identifications made on the record.

    This functions similarly to the pretty-printer, where entries are stored in dictionaries.
    The difference is that in some cases, simply a result is stored in the dictionary, as a
    convenience instead of calling a function.

    """

    def __init__(self):
        """Initialize the identifier."""
        self.record_type_iders = {
            RESULT: self.identify_result,
            ASYNC_EXEC: self.identify_async_exec,
            ASYNC_NOTIFY: self.identify_async_notify,
            STREAM_CONSOLE: self.identify_stream_console
            }
        self.result_iders = {
            RESULT_CLASS_ERROR: self.identify_result_error,
            RESULT_CLASS_DONE: self.identify_result_done,
            # Done and running are to be treated the same way.
            RESULT_CLASS_RUNNING: self.identify_result_done,
            RESULT_CLASS_EXIT: self.identify_result_exit
            }
        self.result_done_iders = {
            "time": ["time"],
            "bkpt": ["breakpoint-created"],
            "wpt": ["watchpoint-created"],
            "hw-awpt": ["access-watchpoint-created"],
            "hw-rwpt": ["read-watchpoint-created"],
            "value": ["value"],
            "stack": ["stack"],
            "thread-id": ["thread-id"],
            "BreakpointTable": ["breakpoint-table"],
            "name": ["var-created"],
            "children": ["var-list-children"],
            "type": ["var-info-type"],
            "features": ["feature-list"],
            "groups": ["thread-groups-list"],
            "threads": ["threads-list"],
            "source-path": ["source-path"],
            "path": ["path"],
            "cwd": ["cwd"],
            "frame": ["frame"],
            "depth": ["stack-depth"],
            "stack-args": ["stack-args"],
            "variables": ["stack-variables"],
            "asm_insns": ["asm-instructions"],
            "changed-registers": ["changed-registers"],
            "register-names": ["register-names"],
            "register-values": ["register-values"]
            }
        self.exec_iders = {
            "stopped": self.identify_exec_stopped,
            "running": self.identify_exec_running
            }
        self.exec_stopped_iders = {
            "breakpoint-hit": ["breakpoint-hit"],
            "watchpoint-trigger": ["watchpoint-trigger"],
            "access-watchpoint-trigger": ["access-watchpoint-trigger"],
            "read-watchpoint-trigger": ["read-watchpoint-trigger"],
            "watchpoint-scope": ["watchpoint-scope"],
            "end-stepping-range": ["step-done"],
            "exit-signalled": ["exit-signal"],
            "exited": ["exited"],
            "exited-normally": ["normal-exit"],
            "signal-received": ["signal-received"],
            "location-reached": ["location-reached"],
            "function-finished": ["function-finished"]
            }
        self.notify_iders = {
            "thread-group-added": ["thread-group-added"],
            "thread-group-started": ["thread-group-started"],
            "thread-group-exited": ["thread-group-exited"],
            "thread-created": ["thread-created"],
            "thread-exited": ["thread-exited"],
            "library-loaded": ["library-loaded"]
            }

    def _call_or_ret(self, item, *args):
        """Helper function to either call an item and return the result, or simply return it."""
        if callable(item):
            return item(*args)
        return item

    def identify(self, record):
        """Attempt to identify a record.

        record is the record to identify.

        This returns False if the record cannot be identified; otherwise it returns a list of
        identifications. The first item will be the record type identification, and subsequent entries
        will be based on the specific record identifiers. If no identification beyond the record
        type can be made, the result will be [<record type>, False].

        """
        if record.record_type in self.record_type_iders:
            ident = self.record_type_iders[record.record_type](record)
            if ident:
                return [record.record_type] + ident
            return [record.record_type, False]
        return False

    def identify_result(self, record):
        """Identify a result record."""
        if record.result_class in self.result_iders:
            return self.result_iders[record.result_class](record)
        return False

    def identify_result_error(self, record):
        """Identify an error result."""
        return ["error"]

    def identify_result_exit(self, record):
        """Identify an exit reuslt."""
        return ["exit"]

    def identify_result_done(self, record):
        """Invoke sub-identifiers to identify a done result."""
        matches = ["done"]
        for key in record.results:
            if key in self.result_done_iders:
                matches += self._call_or_ret(self.result_done_iders[key], record)
        return matches

    def identify_async_exec(self, record):
        """Identify an exec async record."""
        if record.output_class in self.exec_iders:
            return self.exec_iders[record.output_class](record)
        return False

    def identify_exec_stopped(self, record):
        """Identify an exec stopped record."""
        matches = ["stopped"]
        if "reason" in record.output and record.output["reason"] in self.exec_stopped_iders:
            return matches + self._call_or_ret(self.exec_stopped_iders[record.output["reason"]],
                                               record)
        else:
            if "frame" in record.output:
                return matches + ["frame"]
            return matches

    def identify_exec_running(self, record):
        """Identify an exec running record."""
        return ["running"]

    def identify_async_notify(self, record):
        """Identify a notify async record."""
        if record.output_class in self.notify_iders:
            return self._call_or_ret(self.notify_iders[record.output_class], record)
        return False

    def identify_stream_console(self, record):
        """Identify a stream console record."""
        return ["stream-console"]

    

    
