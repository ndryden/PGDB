"""PGDB scalable binary distribution (SBD) system.

This handles deploying files via MRNet instead of the parallel filesystem.

"""

import os.path, mmap, struct, re, socket
import posix_ipc
from gdb_shared import GDBMessage, FILE_DATA
from conf import gdbconf

class SBDFE:
    """Front-end SBD system."""

    def __init__(self, comm):
        """Initialization.

        comm is the FE comm object.

        """
        self.comm = comm
        self.loaded_files = set()

    def load_file(self, filename):
        """Load a file and broadcast it.

        This will attempt to load a file, and broadcasts either the file or an
        error notice. If the file has already been loaded, this does nothing.

        """
        if filename in self.loaded_files:
            # File has been broadcast to everyone.
            # TODO: Time this out somehow so that further requests can be made.
            return
        if not os.path.isfile(filename):
            print "Invalid SBD load file request for '{0}'".format(filename)
            self.comm.send(GDBMessage(FILE_DATA, filename = filename,
                                      data = None, error = True),
                           self.comm.broadcast)
            return
        try:
            f = open(filename, "rb")
        except IOError as e:
            print "Cannot open {0} for SBD load file: {1}.".format(filename,
                                                                   e.strerror)
            self.comm.send(GDBMessage(FILE_DATA, filename = filename,
                                      data = None, error = True),
                           self.comm.broadcast)
            return
        try:
            data = f.read()
        except IOError as e:
            print "Cannot read {0} for SBD load file: {1}.".format(filename,
                                                                   e.strerror)
            self.comm.send(GDBMessage(FILE_DATA, filename = filename,
                                      data = None, error = True),
                           self.comm.broadcast)
            return
        f.close()
        self.loaded_files.add(filename)
        self.comm.send(GDBMessage(FILE_DATA, filename = filename,
                                  data = data, error = False),
                       self.comm.broadcast)

class SBDBE:
    """Back-end SBD system."""

    def __init__(self, comm):
        """Initialize the SBD system.

        comm is the BE comm object.

        """
        self.comm = comm
        # Regex for checking whether to load a file.
        self.load_file_re = re.compile(r".*\.so.*")
        # Stores data for LOAD_FILE/FILE_DATA. Indexed by filename.
        # Entries are None when there is no data, False when error was received,
        # and data otherwise.
        self.load_files = {}
        # Set of executable names for all processes.
        self.load_file_bins = set()
        self.current_load_file = None
        # Shared memory and semaphore for communicating with GDB for loading files.
        hostname = socket.gethostname()
        self.gdb_semaphore = posix_ipc.Semaphore("/PGDBSemaphore" + hostname,
                                                 posix_ipc.O_CREX)
        try:
            self.gdb_shmem = posix_ipc.SharedMemory("/PGDBMem" + hostname,
                                                    posix_ipc.O_CREX,
                                                    size = gdbconf.sbd_shmem_size)
        except posix_ipc.ExistentialError as e:
            self.gdb_semaphore.unlink()
            self.gdb_semaphore.close()
            raise e
        try:
            self.gdb_mem = mmap.mmap(self.gdb_shmem.fd, self.gdb_shmem.size)
        except mmap.error as e:
            self.gdb_semaphore.unlink()
            self.gdb_semaphore.close()
            self.gdb_shmem.close_fd()
            self.gdb_shmem.unlink()
            raise e
        # Created acquired, so release.
        self.gdb_semaphore.release()

    def set_executable_names(self, names):
        """Set the names of all the binaries of the processes under control.

        names is a list of all the executable names.
        This should be called only once, as it overwrites the prior set.

        """
        self.load_file_bins = set(names)

    def load_file(self, filename):
        """Send a request for a file to be loaded."""
        filename = os.path.abspath(filename)
        if filename in self.load_files:
            self.file_data_respond(filename)
            self.gdb_semaphore.release()
            return
        self.load_files[filename] = None
        self.current_load_file = filename
        self.comm.send(GDBMessage(LOAD_FILE, filename = filename,
                                  rank = self.comm.get_mpiranks()),
                       self.comm.frontend)

    def load_file_check(self, filename):
        """Check whether we should load the filename."""
        filename = os.path.abspath(filename)
        base = os.path.basename(filename)
        if base in self.load_file_bins:
            return True
        if base[-4:] == ".gdb" or base[-3:] == ".py":
            return False
        if filename[0:6] == "/lib64":
            # This often causes front-end/back-end mismatches.
            # TODO: Generalize this to a config option.
            return False
        if self.load_file_re.match(base) is not None:
            return True
        return False

    def check_gdb_memory_flag(self):
        """Check whether the GDB process has indicated it wrote something."""
        flag = struct.unpack_from("=B", self.gdb_mem, 1)[0]
        return flag == 1

    def read_memory(self):
        """Read memory from the GDB process."""
        # Clear GDB-DW flag.
        struct.pack_into("=B", self.gdb_mem, 1, 0)
        size = struct.unpack_from("=I", self.gdb_mem, 2)[0]
        if size <= 0:
            print "Invalid read-memory size {0}!".format(size)
            return False
        return struct.unpack_from("={0}s".format(size), self.gdb_mem, 6)[0]

    def write_memory(self, data):
        """Write memory to the GDB process."""
        # Set PGDB-DW flag.
        struct.pack_into("=B", self.gdb_mem, 0, 1)
        size = len(data)
        # size + 1 to account for packing adding a null byte.
        return struct.pack_into("=I{0}s".format(size + 1), self.gdb_mem, 2,
                                size, data)

    def file_data_respond(self, filename):
        """Write the loaded file to shared memory.

        Assumes the file data is in self.load_files[filename] and the semaphore
        has been acquired. This does not release it.

        """
        if filename not in self.load_files or self.load_files[filename] is None:
            return False
        self.write_memory(self.load_files[filename])

    def file_data_handler(self, msg):
        """Handle a response with file data."""
        filename = msg.filename
        if msg.error:
            self.load_files[filename] = "error"
        else:
            self.load_files[filename] = msg.data
        if self.current_load_file != filename:
            # Got response, but not for the currently-requested file.
            return
        self.file_data_respond(filename)
        self.current_load_file = None
        self.gdb_semaphore.release()

    def sbd_check(self):
        """Check for and process a load file request from GDB."""
        try:
            self.gdb_semaphore.acquire(0)
            if self.check_gdb_memory_flag():
                # Read filename.
                filename = self.read_memory()
                if filename and self.load_file_check(filename):
                    self.load_file(filename)
                    # The file_data_handler releases the semaphore after the
                    # file data is received.
                else:
                    self.write_memory("error")
                    self.gdb_semaphore.release()
            else:
                self.gdb_semaphore.release()
        except posix_ipc.BusyError:
            pass

    def cleanup(self):
        """Clean up the SBD."""
        self.gdb_semaphore.unlink()
        self.gdb_semaphore.close()
        self.gdb_mem.close()
        self.gdb_shmem.unlink()
        self.gdb_shmem.close_fd()
