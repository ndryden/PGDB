"""An interface to GDB using its Machine Interface."""

import subprocess
import fcntl
import os
import select
from gdbmi_parser import GDBMIParser

class GDBMachineInterface:
    """Manages the GDB Machine Interface."""

    def __init__(self, gdb="gdb", gdb_args=None, env=None):
        """Initialize a new machine interface session with GDB."""
        gdb_args = gdb_args or []
        env = env or {}
        env.update(os.environ)
        args = [gdb, '--quiet', '--nx', '--nw', '--interpreter=mi2'] + gdb_args
        self.process = subprocess.Popen(
            args=args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            close_fds=True,
            env=env
            )
        flags = fcntl.fcntl(self.process.stdout, fcntl.F_GETFL)
        fcntl.fcntl(self.process.stdout, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        self.buffer = "" # Buffer for output from GDB.
        self.parser = GDBMIParser() # Parser for output from GDB.

    def _read(self, timeout=0):
        """A generator to read data from GDB's stdout."""
        while True:
            ready = select.select([self.process.stdout], [], [], timeout)
            if not ready[0]:
                # No data to read.
                break
            try:
                yield self.process.stdout.read()
                # Don't block on subsequent reads while we still have data.
                timeout = 0
            except IOError:
                break

    def _write(self, data):
        """Write data to GDB."""
        try:
            self.process.stdin.write(data + "\n")
            self.process.stdin.flush()
        except IOError:
            return False
        return True

    def send(self, command):
        """Send a command to GDB.

        command is a Command object with the data to send.

        """
        return self._write(command.generate_mi_command())

    def read(self, timeout=0):
        """Generator to read, parse, and return data from GDB."""
        for data in self._read(timeout):
            self.buffer += data
            while True:
                (before, newline, self.buffer) = self.buffer.rpartition("\n")
                if newline:
                    records = self.parser.parse_output(before)
                    for record in records:
                        yield record
                else:
                    return

    def is_running(self):
        """Check if the GDB process is running."""
        return self.process.poll() is None

    def get_pid(self):
        """Return the PID of the GDB process."""
        return self.process.pid
