"""An interface to GDB using its Machine Interface."""

import subprocess
import fcntl
import os
import select
from gdbmi_parser import *

class GDBMachineInterface:
    """Manages the GDB Machine Interface."""

    def __init__(self, gdb = "gdb", gdb_args = []):
        """Initialize a new machine interface session with GDB."""
        self.process = subprocess.Popen(
            args = [gdb, '--quiet', '--nx', '--nw', '--interpreter=mi2'] + gdb_args,
            stdin = subprocess.PIPE,
            stdout = subprocess.PIPE,
            close_fds = True,
            env = os.environ
            )
        f = fcntl.fcntl(self.process.stdout, fcntl.F_GETFL)
        fcntl.fcntl(self.process.stdout, fcntl.F_SETFL, f | os.O_NONBLOCK)

        self.token = 0 # This is used to identify associated output.
        self.buffer = "" # Buffer for output from GDB.
        self.parser = GDBMIParser() # Parser for output from GDB.

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

    def send(self, command, token = None):
        """Send data to GDB and return the associated token."""
        if not token:
            token = self.token
            token_str = "{0:08d}".format(self.token)
            self.token += 1
        else:
            token_str = str(token)
        self._write(token_str + command)
        return token

    def read(self, timeout = 0):
        """Generator to read, parse, and return data from GDB."""
        for data in self._read(timeout):
            self.buffer += data
            while True:
                (before, nl, self.buffer) = self.buffer.rpartition("\n")
                if nl:
                    records = self.parser.parse_output(before)
                    for record in records:
                        yield record
                else:
                    return

    def is_running(self):
        """Check if the GDB process is running."""
        return self.process.poll() is None
