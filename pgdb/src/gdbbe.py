"""The back-end daemon invoked by LaunchMON.

This handles initializing the back-end side of the LaunchMON and MRNet
communication systems, deploying GDB, and sending commands and data back
and forth.

"""

from __future__ import print_function
from conf import gdbconf
from comm import CommunicatorBE
from gdb_shared import *
from lmon.lmonbe import LMON_be
import mi.gdbmi_parser as gdbparser
from mi.gdbmi import GDBMachineInterface
from mi.varobj import VariableObject, VariableObjectManager
from mi.commands import Command
from mi.gdbmiarec import (GDBMIAggregatedRecord, combine_records,
                          combine_aggregated_records)
from mi.gdbmi_recordhandler import GDBMIRecordHandler
from interval import Interval
from varprint import VariablePrinter
from sbd import SBDBE
import signal
import os
import os.path
import mmap
import struct
import time
import sys
import posix_ipc

class GDBBE:
    """The back-end GDB daemon process."""

    def init_gdb(self):
        """Initialize GDB-related things, and launch the GDB process."""
        # Indexed by MPI rank.
        self.varobjs = {}
        # Maps tokens to MPI rank.
        self.token_rank_map = {}
        self.record_handler = GDBMIRecordHandler()
        self.record_handler.add_type_handler(
            self._watch_thread_created,
            set([gdbparser.ASYNC_NOTIFY_THREAD_CREATED]))
        self.startup_stop_hid = self.record_handler.add_type_handler(
            self._watch_startup_stop,
            set([gdbparser.ASYNC_EXEC_STOPPED]))
        gdb_env = {}
        if gdbconf.use_sbd:
            self.sbd = SBDBE(self.comm)
            gdb_env["LD_PRELOAD"] = gdbconf.sbd_bin
        else:
            self.sbd = None

        enable_pprint_cmd = Command("enable-pretty-printing")
        enable_target_async_cmd = Command("gdb-set",
                                          args=["target-async", "on"])
        disable_pagination_cmd = Command("gdb-set", args=["pagination", "off"])
        enable_non_stop_cmd = Command("gdb-set", args=["non-stop", "on"])
        add_inferior_cmd = Command("add-inferior")
        self.gdb = GDBMachineInterface(gdb=gdbconf.gdb_path,
                                       gdb_args=["-x", gdbconf.gdb_init_path],
                                       env=gdb_env)
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
            if not self.run_gdb_command(add_inferior_cmd, no_thread=True):
                raise RuntimeError('Cound not add inferior i{0}!'.format(i - 1))

        # Maps MPI ranks to associated threads and vice-versa.
        self.rank_thread_map = {procs[0].mpirank: [1]}
        self.thread_rank_map = {1: procs[0].mpirank}

        if self.sbd:
            # Set up the list of executables for load file checking.
            self.sbd.set_executable_names(
                [os.path.basename(proc.pd.executable_name) for proc in procs])

        # Attach processes.
        for proc in procs:
            if not self.run_gdb_command(
                    Command("target-attach",
                            opts={'--thread-group':
                                  self.rank_inferior_map[proc.mpirank]},
                            args=[proc.pd.pid]),
                    proc.mpirank, no_thread=True):
                raise RuntimeError("Could not attach to rank {0}!".format(
                    proc.mpirank))
            self.varobjs[proc.mpirank] = VariableObjectManager()
            # Cludge to fix GDB not outputting records for the i1 attach.
            if self.rank_inferior_map[proc.mpirank] == 'i1':
                time.sleep(0.1)

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

    def _watch_startup_stop(self, record, **kwargs):
        """Handle watching for initial inferior stops during startup."""
        self.startup_done_count += 1
        if self.startup_done_count == self.comm.get_proctab_size():
            self.doing_startup = False
            self.record_handler.remove_handler(self.startup_stop_hid)

    def kill_inferiors(self):
        """Terminate all targets being debugged.

        This sends SIGTERM.

        """
        for proc in self.comm.get_proctab():
            os.kill(proc.pd.pid, signal.SIGTERM)

    def run_gdb_command(self, command, ranks=None, no_thread=False):
        """Run a GDB command.

        command is a Command object representing the command.
        ranks is an Interval of the ranks to run the command on.
        If ranks is None, run on the current inferior.
        If no_thread is True, this does not specify a particular thread.

        Returns True on success, False on error.

        """
        if isinstance(ranks, int):
            # Special case for a single int.
            # Toss it in a list; don't need a full Interval.
            ranks = Interval(ranks)
        if ranks is None:
            self.token_rank_map[command.token] = self.comm.get_mpiranks()
            return self.gdb.send(command)
        else:
            for rank in ranks:
                if rank in self.rank_inferior_map:
                    # Most recent option with same name takes precedence.
                    if (not no_thread and
                        rank in self.rank_thread_map and
                        command.get_opt('--thread') is None):
                        command.add_opt('--thread',
                                        self.rank_thread_map[rank][0])
                    if not self.gdb.send(command):
                        return False
            self.token_rank_map[command.token] = ranks
        return True

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
        self.doing_startup = True
        self.startup_done_count = 0
        self.startup_arecs = []
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
        if self.sbd:
            self.sbd.cleanup()

    def __del__(self):
        """Invoke shutdown()."""
        # Exception guard if we have an error before comm init.
        try:
            self.shutdown()
        except AttributeError:
            pass

    def die_handler(self, msg):
        """Handle a die message by exiting."""
        sys.exit("Told to die.")

    def cmd_handler(self, msg):
        """Handle a CMD message by running the command.

        The message contains the following fields:
        command - A Command object to run.
        ranks - An optional interval of ranks on which to run.

        """
        if self.doing_startup:
            print("Ignoring command during startup.")
            return
        if msg.command.command == "gdb-exit":
            # Special case for quit.
            self.quit = True
        ranks = self.comm.get_mpiranks()
        if hasattr(msg, "ranks"):
            ranks = msg.ranks
        if not self.run_gdb_command(msg.command, ranks):
            # TODO: Send die message.
            print("Managed to get a bad command '{0}'.".format(msg.command))

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
        """Handle the varprint message and begin sequence."""
        self.variable_printer.varprint_handler(msg)

    def is_filterable(self, record):
        """Check whether a given record can be filtered."""
        record_set = record.record_subtypes.union([record.record_type])
        if record_set.intersection(self.filters):
            return True
        return False

    def file_data_handler(self, msg):
        """Handle a response with file data."""
        if self.sbd:
            self.sbd.file_data_handler(msg)
        else:
            print("Got SBD file data when SBD is not enabled")

    def main(self):
        """Main send/receive loop.

        This receives data on MRNet (non-blocking), processes the messages,
        and then sends any data that was read from GDB. This then sleeps for a
        short while to avoid heavy CPU use.

        """
        while True:
            if self.quit:
                break

            if self.sbd:
                # Check for data from the GDB process for LOAD_FILE.
                self.sbd.sbd_check()

            msg = self.comm.recv(blocking=False)
            if msg is not None:
                # Received data.
                if msg.msg_type in self.msg_handlers:
                    self.msg_handlers[msg.msg_type](msg)
                else:
                    print("Got a message {0} with no handler.".format(
                        msg.msg_type))

            records = []
            ranks = []
            for record in self.gdb.read():
                self.record_handler.handle(record)
                if not self.is_filterable(record):
                    records.append(record)
                    if record.token and record.token in self.token_rank_map:
                        ranks.append(self.token_rank_map[record.token])
                    else:
                        ranks.append(self.comm.get_mpiranks())
            if records:
                arecs = combine_records(records, ranks)
                if self.doing_startup:
                    self.startup_arec = combine_aggregated_records(
                        self.startup_arecs + arecs)
                else:
                    if not self.doing_startup and self.startup_arecs:
                        arecs = combine_aggregated_records(
                            self.startup_arecs + arecs)
                        self.comm.send(GDBMessage(OUT_MSG, record=arecs),
                                       self.comm.frontend)
                        self.startup_arecs = None
                    else:
                        self.comm.send(GDBMessage(OUT_MSG, record=arecs),
                                       self.comm.frontend)

            # Sleep a bit to reduce banging on the CPU.
            time.sleep(0.01)
        # Wait for GDB to exit.
        exited = False
        while not exited:
            exited = not self.gdb.is_running()
        # Shut everything else down.
        self.shutdown()

if __name__ == "__main__":
    # This is run by LaunchMON.
    gdbbe = GDBBE()
    gdbbe.main()
