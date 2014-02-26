"""The back-end daemon invoked by LaunchMON.

This handles initializing the back-end side of the LaunchMON and MRNet communication systems,
deploying GDB, and sending commands and data back and forth.

"""

from conf import gdbconf
from comm import *
from gdb_shared import *
from lmon.lmonbe import *
import mi.gdbmi_parser as gdbparser
from mi.gdbmi import *
from mi.varobj import VariableObject, VariableObjectManager
from mi.commands import Command
from mi.gdbmiarec import GDBMIAggregatedRecord, combine_records
from mi.gdbmi_recordhandler import GDBMIRecordHandler
from interval import Interval
from varprint import VariablePrinter
import signal, os, os.path, mmap, struct, socket, re
import posix_ipc

class GDBBE:
    """The back-end GDB daemon process."""

    def init_gdb(self):
        """Initialize GDB-related things, including launching the GDB process."""
        # Indexed by MPI rank.
        self.varobjs = {}
        # Maps tokens to MPI rank.
        self.token_rank_map = {}
        self.record_handler = GDBMIRecordHandler()
        self.record_handler.add_type_handler(self._watch_thread_created,
                                             set([gdbparser.ASYNC_NOTIFY_THREAD_CREATED]))
        # Regex for checking whether to load a file.
        self.load_file_re = re.compile(r".*\.so.*")
        # Stores data for LOAD_FILE/FILE_DATA. Indexed by filename.
        # Entries are None when there is no data, False when error was received,
        # and data otherwise.
        self.load_files = {}
        self.current_load_file = None
        # Shared memory and semaphore for communicating with GDB for loading files.
        hostname = socket.gethostname()
        self.gdb_semaphore = posix_ipc.Semaphore("/PGDBSemaphore" + hostname,
                                                 posix_ipc.O_CREX)
        # Use 32 MiB. TODO: Move this to config.
        try:
            self.gdb_shmem = posix_ipc.SharedMemory("/PGDBMem" + hostname,
                                                    posix_ipc.O_CREX,
                                                    size = 33554432)
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

        enable_pprint_cmd = Command("enable-pretty-printing")
        enable_target_async_cmd = Command("gdb-set", args = ["target-async", "on"])
        disable_pagination_cmd = Command("gdb-set", args = ["pagination", "off"])
        enable_non_stop_cmd = Command("gdb-set", args = ["non-stop", "on"])
        add_inferior_cmd = Command("add-inferior")
        self.gdb = GDBMachineInterface(gdb = gdbconf.gdb_path,
                                       gdb_args = ["-x", gdbconf.gdb_init_path],
                                       env = {"LD_PRELOAD": "/home/dryden2/PGDB/pgdb/load_file.so"})
        procs = self.comm.get_proctab()
        # Set up GDB.
        if not self.run_gdb_command(enable_pprint_cmd):
            raise RuntimeError("Could not enable pretty printing!")
        if not self.run_gdb_command(enable_target_async_cmd):
            raise RuntimeError("Could not enable target-async!")
        if not self.run_gdb_command(disable_pagination_cmd):
            raise RuntimeError("Could not disable pagination!")
        if not self.run_gdb_command(enable_non_stop_cmd):
            raise RuntimeError("Could not enable non-stop!")

        # Create inferiors and set up MPI rank/inferior map.
        # First inferior is created by default.
        self.rank_inferior_map = {procs[0].mpirank: 'i1'}
        self.inferior_rank_map = {'i1': procs[0].mpirank}
        i = 2
        for proc in procs[1:]:
            # Hackish: Assume that the inferiors follow the iN naming scheme.
            self.rank_inferior_map[proc.mpirank] = 'i' + str(i)
            self.inferior_rank_map['i' + str(i)] = proc.mpirank
            i += 1
            if not self.run_gdb_command(add_inferior_cmd, no_thread = True):
                raise RuntimeError('Cound not add inferior i{0}!'.format(i - 1))

        # Maps MPI ranks to associated threads and vice-versa.
        self.rank_thread_map = {procs[0].mpirank: [1]}
        self.thread_rank_map = {1: procs[0].mpirank}

        # Set up the list of executables for load file checking.
        self.load_file_bins = set()
        for proc in procs:
            self.load_file_bins.add(os.path.basename(proc.pd.executable_name))

        # Attach processes.
        for proc in procs:
            if not self.run_gdb_command(Command("target-attach",
                                                opts = {'--thread-group': self.rank_inferior_map[proc.mpirank]},
                                                args = [proc.pd.pid]),
                                        proc.mpirank, no_thread = True):
                raise RuntimeError("Could not attach to rank {0}!".format(proc.mpirank))
            self.varobjs[proc.mpirank] = VariableObjectManager()

    def _watch_thread_created(self, record, **kwargs):
        """Handle watching thread creation."""
        inferior = record.thread_group_id
        thread_id = int(record.thread_id)
        rank = self.inferior_rank_map[inferior]
        if rank in self.rank_thread_map:
            self.rank_thread_map[rank].append(thread_id)
        else:
            self.rank_thread_map[rank] = [thread_id]
            # Always ensure smallest thread is first.
            self.rank_thread_map[rank].sort()
        self.thread_rank_map[thread_id] = rank

    def kill_inferiors(self):
        """Terminate all targets being debugged.

        This sends SIGTERM.

        """
        for proc in self.proctab:
            os.kill(proc.pd.pid, signal.SIGTERM)

    def run_gdb_command(self, command, ranks = None, token = None, no_thread = False):
        """Run a GDB command.

        command is a Command object representing the command.
        ranks is an Interval of the ranks to run the command on.
        If ranks is None, run on the current GDB inferior.
        token is the optional token to use.

        Returns a dictionary, indexed by ranks, of the tokens used.
        If running on the current inferior, the "rank" is -1.

        """
        if isinstance(ranks, int):
            # Special case for a single int.
            # Toss it in a list; don't need a full Interval.
            ranks = [ranks]
        tokens = {}
        if not ranks:
            # Send to the current inferior.
            tokens[-1] = self.gdb.send(command.generate_mi_command(), token)
            if tokens[-1] is None:
                print "GDB error, exiting."
                self.quit = True
                return
        else:
            for rank in ranks:
                if rank in self.rank_inferior_map:
                    # Most recent option with same name takes precedence.
                    if (not no_thread and
                        rank in self.rank_thread_map and
                        command.get_opt('--thread') is None):
                        command.add_opt('--thread', self.rank_thread_map[rank][0])
                    ret_token = self.gdb.send(command.generate_mi_command(),
                                              token)
                    if ret_token is None:
                        print "GDB error, exiting."
                        self.quit = True
                        return
                    tokens[rank] = ret_token
                    self.token_rank_map[ret_token] = rank
        return tokens

    def init_handlers(self):
        """Initialize message handlers used on data we receive over MRNet."""
        self.msg_handlers = {
            DIE_MSG: self.die_handler,
            CMD_MSG: self.cmd_handler,
            FILTER_MSG: self.filter_handler,
            UNFILTER_MSG: self.unfilter_handler,
            VARPRINT_MSG: self.varprint_handler,
            KILL_MSG: self.kill_handler,
            FILE_DATA: self.file_data_handler,
            }

    def init_filters(self):
        """Initialize default filters."""
        self.filters = set()
        #an_lower = ASYNC_NOTIFY.lower()
        #self.filters = [
        #    (an_lower, "shlibs-updated"),
        #    (an_lower, "shlibs-added"),
        #    (an_lower, "shlibs-removed"),
        #    (an_lower, "library-loaded"),
        #    (an_lower, "thread-created"),
        #    (an_lower, "thread-group-added"),
        #    (an_lower, "thread-group-started"),
        #    (RESULT.lower(), "exit")
        #    ]

    def __init__(self):
        """Initialize LaunchMON, MRNet, GDB, and other things."""
        self.is_shutdown = False
        self.quit = False
        self.token_handlers = {}
        self.comm = CommunicatorBE()
        if not self.comm.init_lmon(sys.argv):
            sys.exit(1)
        if not self.comm.init_mrnet():
            # TODO: This should cleanly terminate LaunchMON, but does not.
            sys.exit(1)
        self.init_gdb()
        self.init_handlers()
        self.init_filters()
        self.variable_printer = VariablePrinter(self)

    def shutdown(self):
        """Cleanly shut things down if we have not already done so."""
        if not self.comm.is_shutdown():
            self.comm.shutdown()
        self.gdb_semaphore.unlink()
        self.gdb_semaphore.close()
        self.gdb_mem.close()
        self.gdb_shmem.unlink()
        self.gdb_shmem.close_fd()

    def __del__(self):
        """Invoke shutdown()."""
        # Exception guard if we have an error before comm init.
        try:
            self.shutdown()
        except AttributeError: pass

    def die_handler(self, msg):
        """Handle a die message by exiting."""
        sys.exit("Told to die.")

    def cmd_handler(self, msg):
        """Handle a CMD message by running the command.

        The message contains the following fields:
        command - A Command object to run.
        ranks - An optional interval of ranks on which to run.
        token - An optional token to use.

        """
        if msg.command.command == "gdb-exit":
            # Special case for quit.
            self.quit = True
        token = None
        if hasattr(msg, "token"):
            token = msg.token
        ranks = self.comm.get_mpiranks()
        if hasattr(msg, "ranks"):
            ranks = msg.ranks
        if not self.run_gdb_command(msg.command, ranks, token = token):
            # TODO: Send die message.
            print "Managed to get a bad command '{0}'.".format(msg.command)

    def kill_handler(self, msg):
        """Handle a kill message, killing all processes."""
        self.kill_inferiors()

    def filter_handler(self, msg):
        """Handle a filter message by adding the filter."""
        self.filters.update(msg.filter_types)

    def unfilter_handler(self, msg):
        """Handle an unfilter message by removing the filter."""
        self.filters.difference_update(msg.filter_types)

    def varprint_handler(self, msg):
        """Handle the varprint message and begin sequence. See VariablePrinter."""
        self.variable_printer.varprint_handler(msg)

    def is_filterable(self, record):
        """Check whether a given record can be filtered."""
        record_set = record.record_subtypes.union([record.record_type])
        if record_set.intersection(self.filters):
            return True
        return False

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
        if self.load_file_re.match(base) is not None:
            return True
        return False

    def check_gdb_memory_flag(self):
        flag = struct.unpack_from("=B", self.gdb_mem, 1)[0]
        return flag == 1

    def read_memory(self):
        # Clear GDB-DW flag.
        struct.pack_into("=B", self.gdb_mem, 1, 0)
        size = struct.unpack_from("=I", self.gdb_mem, 2)[0]
        if size <= 0:
            print "Invalid read-memory size {0}!".format(size)
            return False
        return struct.unpack_from("={0}s".format(size), self.gdb_mem, 6)[0]

    def write_memory(self, data):
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

    def main(self):
        """Main send/receive loop.

        This receives data on MRNet (non-blocking), processes the messages, and then sends any
        data that was read from GDB. This then sleeps for a short while to avoid heavy CPU use.

        """
        while True:
            if self.quit:
                break

            # Check for data from the GDB process for LOAD_FILE.
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
            # TODO: Check for memory leaks relating to these.
            msg = self.comm.recv(blocking = False)
            if msg is not None:
                # Received data.
                if msg.msg_type in self.msg_handlers:
                    self.msg_handlers[msg.msg_type](msg)
                else:
                    print "Got a message {0} with no handler.".format(msg.msg_type)

            records = []
            ranks = []
            for record in self.gdb.read():
                self.record_handler.handle(record)
                if not self.is_filterable(record):
                    records.append(record)
                    if record.token and record.token in self.token_rank_map:
                        ranks.append(self.token_rank_map[record.token])
                    else:
                        ranks.append(-1)
            if records:
                arecs = combine_records(records, ranks)
                self.comm.send(GDBMessage(OUT_MSG, record = arecs), self.comm.frontend)

            # Sleep a bit to reduce banging on the CPU.
            time.sleep(0.01)
        # Wait for GDB to exit.
        exited = False
        while not exited:
            exited = not self.gdb.is_running()
        # Shut everything else down.
        self.shutdown()

def run():
    """Simple function to run the backend."""
    gdbbe = GDBBE()
    gdbbe.main()

if __name__ == "__main__":
    run()
