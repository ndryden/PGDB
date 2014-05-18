"""Primary communication class for managing LaunchMON and MRNet communication."""

import cPickle, os, sys, socket, threading, time, traceback, zlib
from gdb_shared import *
from conf import gdbconf
from lmon import lmon
from lmon.lmonfe import LMON_fe
from lmon.lmonbe import LMON_be
from MRNet import MRN
from interval import Interval

class Communicator (object):
    """Basic communicator class."""

    # Special names for certain intervals.
    frontend = "FRONTEND"
    broadcast = "BROADCAST"

    def __init__(self, locking = False):
        """Initialize things."""
        self.lmon = None
        self.mrnet = None
        self.been_shutdown = False
        self.recv_stash = []
        self.use_locking = locking
        self.packet_count = 0
        self.send_time_sum = 0
        if self.use_locking:
            self.lock = threading.RLock()

    def _lock(self):
        """If using locking, acquire the lock. Otherwise do nothing.

        Note that this does not quite work like the with statement, and things
        will break if exceptions are raised.

        """
        if self.use_locking:
            self.lock.acquire()

    def _unlock(self):
        """If using locking, release the lock. Otherwise do nothing."""
        if self.use_locking:
            self.lock.release()

    def init_lmon(self):
        """Initialize LaunchMON. Should be over-ridden by children."""
        raise NotImplemented

    def _init_mpiranks(self):
        """Initialize the list of MPI ranks."""
        self.mpiranks = []
        for proc in self.proctab:
            self.mpiranks.append(proc.mpirank)

    def _enable_mrnet_perf_data(self):
        """Enable MRNet performance data."""
        if gdbconf.mrnet_collect_perf_data:
            self.mrnet.enable_PerformanceData(MRN.PERFDATA_MET_NUM_BYTES,
                                              MRN.PERFDATA_CTX_SEND)
            self.mrnet.enable_PerformanceData(MRN.PERFDATA_MET_NUM_PKTS,
                                              MRN.PERFDATA_CTX_SEND)
            self.mrnet.enable_PerformanceData(MRN.PERFDATA_MET_NUM_BYTES,
                                              MRN.PERFDATA_CTX_RECV)
            self.mrnet.enable_PerformanceData(MRN.PERFDATA_MET_NUM_PKTS,
                                              MRN.PERFDATA_CTX_RECV)

    def _disable_mrnet_perf_data(self):
        """Disable MRNet performance data."""
        if gdbconf.mrnet_collect_perf_data:
            self.mrnet.disable_PerformanceData(MRN.PERFDATA_MET_NUM_BYTES,
                                               MRN.PERFDATA_CTX_SEND)
            self.mrnet.disable_PerformanceData(MRN.PERFDATA_MET_NUM_PKTS,
                                               MRN.PERFDATA_CTX_SEND)
            self.mrnet.disable_PerformanceData(MRN.PERFDATA_MET_NUM_BYTES,
                                               MRN.PERFDATA_CTX_RECV)
            self.mrnet.disable_PerformanceData(MRN.PERFDATA_MET_NUM_PKTS,
                                               MRN.PERFDATA_CTX_RECV)

    def _log_mrnet_perf_data(self):
        """Log MRNet performance data."""
        if gdbconf.mrnet_collect_perf_data:
            self.mrnet.print_PerformanceData(MRN.PERFDATA_MET_NUM_BYTES,
                                             MRN.PERFDATA_CTX_SEND)
            self.mrnet.print_PerformanceData(MRN.PERFDATA_MET_NUM_PKTS,
                                             MRN.PERFDATA_CTX_SEND)
            self.mrnet.print_PerformanceData(MRN.PERFDATA_MET_NUM_BYTES,
                                             MRN.PERFDATA_CTX_RECV)
            self.mrnet.print_PerformanceData(MRN.PERFDATA_MET_NUM_PKTS,
                                             MRN.PERFDATA_CTX_RECV)
            print "Received {0} packets. Average send time = {1}.".format(self.packet_count, self.send_time_sum / self.packet_count)

    def init_mrnet(self):
        """Initialize MRNet. Should be over-ridden by children."""
        raise NotImplemented

    def shutdown(self):
        """Shut down the comm infrastructure. Should be over-ridden by children."""
        raise NotImplemented

    def is_shutdown(self):
        """Return whether the comm instrastructure is shut down."""
        return self.been_shutdown

    def _init_shared_mrnet(self):
        """Initialze some common MRNet stuff."""
        self._init_mrnet_streams()

    def get_proctab_size(self):
        """Return the size of the process table from LaunchMON"""
        return self.proctab_size

    def get_proctab(self):
        """Return the process table from LaunchMON."""
        return self.proctab

    def get_lmon_hosts(self):
        """Return the set of hosts on which LaunchMON runs."""
        return list(set(map(lambda x: x.pd.host_name, self.proctab)))

    def get_mpiranks(self):
        """Return an interval of MPI ranks. If on the back-end, this is local only."""
        return Interval(lis = self.mpiranks)

    def _multi_payload_split(self, msg):
        """Given a message, split it into multi-messages if needed."""
        if len(msg) > gdbconf.multi_len:
            split_len = gdbconf.multi_len
            payloads = [msg[i:i + split_len] for i in range(0, len(msg), split_len)]
            payload_msgs = [GDBMessage(MULTI_MSG, num = len(payloads))]
            for payload in payloads:
                payload_msgs.append(GDBMessage(MULTI_PAYLOAD_MSG, payload = payload))
            serialized_msgs = []
            for payload in payload_msgs:
                serialized_msgs.append(cPickle.dumps(payload, 0))
            return serialized_msgs
        else:
            # Nothing to be done.
            return [msg]

    def _get_stream_for_interval(self, interval):
        """Given an interval, get the appropriate stream for it."""
        if interval == self.frontend:
            return self.mrnet_frontend_stream
        elif interval == self.broadcast:
            return self.mrnet_broadcast_stream
        else:
            if isinstance(interval, int):
                interval = Interval(lis = [interval])
            stream = None
            mrnet_ranks = []
            for rank in interval.members():
                mrnet_ranks.append(self.mpirank_to_mrnrank(rank))
            # Since multiple MPI ranks correspond to one MRNet rank, eliminate duplicates.
            mrnet_ranks = list(set(mrnet_ranks))
            comm = self.mrnet.new_Communicator(mrnet_ranks)
            return self.mrnet.new_Stream(comm,
                                         self.filter_ids[0],
                                         MRN.SFILTER_WAITFORALL,
                                         MRN.TFILTER_NULL)

    def _compress_msg(msg):
        """Compress a message if it is greater than a certain size.

        Currently, compressed messages are not processed by the MRNet filters.
        This limitation can be partially removed: compressed messages that are
        not split into multi-messages can be processed.

        """
        tag = MSG_TAG
        if len(msg) >= gdbconf.compress_threshold:
            msg = zlib.compress(msg, 1)
            tag = COMP_TAG
        return msg, tag

    def send(self, message, targets):
        """Send data over MRNet.

        message is the GDBMessage to send.
        targets is an Interval of the targets to send the data to, or one of
        self.frontend or self.broadcast.

        """
        if gdbconf.mrnet_collect_perf_data:
            message._send_time = time.time()
        msg = cPickle.dumps(message, 0)
        msg, tag = self._compress_msg(msg)
        self._lock()
        send_list = self._multi_payload_split(msg)
        stream = self._get_stream_for_interval(targets)
        for payload in send_list:
            if stream.send(tag, "%s", payload) == -1:
                print "Fatal error on stream send."
                sys.exit(1)
            if stream.flush() == -1:
                print "Fatal error on stream flush."
                sys.exit(1)
        self._unlock()

    def _recv(self, blocking = True):
        """Raw receive function for MRNet."""
        self._lock()
        ret, tag, packet, stream = self.mrnet.recv(blocking)
        if ret == -1:
            print "Terminal network failure on recv."
            sys.exit(1)
        if ret == 0:
            self._unlock()
            return None, None
        ret, serialized = packet.get().unpack("%s")
        if ret == -1:
            print "Could not unpack packet."
            sys.exit(1)
        # Check for filter errors.
        if serialized == "ERROR":
            print "Filter error!"
            sys.exit(1)
        if tag==COMP_TAG:
            msg = zlib.decompress(msg)
        msg = cPickle.loads(serialized)
        # Compute time from sending to receiving.
        if gdbconf.mrnet_collect_perf_data and hasattr(msg, "_send_time"):
            cur = time.time()
            self.packet_count += 1
            self.send_time_sum += max(cur - msg._send_time, 0)
            print "Packet time: {0} - {1} = {2}".format(cur, msg._send_time, cur - msg._send_time)
        self._unlock()
        return msg, stream

    def _recv_multi_message(self, msg):
        """Handle receiving a multi-message."""
        payload = ""
        counter = 0
        while counter != msg.num:
            multi_msg = None
            while not multi_msg:
                # Block, because we know we should get messages.
                recvd, stream = self._recv()
                if not recvd:
                    # This shouldn't happen and may cause bad things.
                    continue
                if recvd.msg_type == MULTI_PAYLOAD_MSG:
                    multi_msg = recvd
                else:
                    self._lock()
                    self.recv_stash.append(recvd)
                    self._unlock()
            payload += multi_msg.payload
            counter += 1
        return cPickle.loads(payload)

    def recv(self, blocking = True, ret_stream = False):
        """Receive data on MRNet. Automatically handles multi-messages."""
        self._lock()
        if len(self.recv_stash) > 0:
            return self.recv_stash.pop(0)
        self._unlock()
        msg, stream = self._recv(blocking)
        if not msg:
            return None
        if msg.msg_type == MULTI_MSG:
            return self._recv_multi_message(msg)
        if ret_stream:
            return msg, stream
        else:
            return msg

class CommunicatorBE (Communicator):
    """Communicator for the back-end."""

    def __init__(self, locking = False):
        Communicator.__init__(self, locking)

    def init_lmon(self, argv):
        """Initialize LaunchMON communication.

        argv is the set of arguments to initialize with.

        """
        self.lmon = LMON_be()
        try:
            self.lmon.init(len(argv), argv)
            self.lmon.regPackForBeToFe(lmon.pack)
            self.lmon.regUnpackForFeToBe(lmon.unpack)
            self.lmon.handshake(None)
            self.lmon.ready(None)
            self.lmon_rank = self.lmon.getMyRank()
            self.lmon_size = self.lmon.getSize()
            self.lmon_master = self.lmon.amIMaster()
            self.proctab_size = self.lmon.getMyProctabSize()
            self.proctab, unused = self.lmon.getMyProctab(self.proctab_size)
        except lmon.LMONException as e:
            e.print_lmon_error()
            traceback.print_exc()
            return False
        self._init_mpiranks()
        return True

    def _wait_for_hello(self):
        """Wait until we receive a HELLO message on MRnet from the front-end."""
        msg, stream = self.recv(ret_stream = True)
        if msg.msg_type != HELLO_MSG:
            print "First message is not hello!"
            sys.exit(1)
        self.mrnet_frontend_stream = stream

    def _init_mrnet_streams(self):
        """Initialize basic MRNet streams."""
        self.broadcast_communicator = None
        self.mrnet_broadcast_stream = None
        self.mrnet_frontend_stream = None # Filled in by back-ends later.

    def init_mrnet(self):
        """Initialize MRNet."""
        local_node_info = None
        try:
            if self.lmon_master:
                # Receive topology information from front-end.
                node_info = self.lmon.recvUsrData(gdbconf.topology_transmit_size)
                # Scatter topology information to back-end.
                # Presently uses a node info size of 256.
                local_node_info = self.lmon.scatter(node_info, 256)
            else:
                # Receive scattered topology.
                local_node_info = self.lmon.scatter(None, 256)
        except lmon.LMONException as e:
            e.print_lmon_error()
            traceback.print_exc()
            return False
        # Construct MRNet arguments and create network.
        argv = [sys.argv[0], # Program name.
                str(local_node_info.host), # Comm node host.
                str(local_node_info.port), # Comm node port.
                str(local_node_info.mrnrank), # Comm node rank.
                socket.getfqdn(), # My host.
                str(local_node_info.be_rank)] # My rank.
        # Initialize.
        self.mrnet = MRN.Network.CreateNetworkBE(6, argv)
        self._init_shared_mrnet()
        self._wait_for_hello()
        return True

    def shutdown(self):
        """Shut down the communication infrastructure."""        
        while not self.mrnet_frontend_stream.is_Closed():
            time.sleep(0.1)
        #del self.mrnet_frontend_stream
        self.mrnet.waitfor_ShutDown()
        del self.mrnet
        self.lmon.finalize()
        self.been_shutdown = True

class CommunicatorFE (Communicator):
    """Communicator for the front-end."""

    def __init__(self, locking = False):
        Communicator.__init__(self, locking)

    def init_lmon(self, attach, **kwargs):
        """Initialize LaunchMON and deploy back-end daemons.

        attach is True to attach to a process.
        - Provide the keyword argument pid, the srun PID.
        attach is False to launch the job.
        - Provide keyword arguments launcher and launcher_args.

        """
        os.environ.update(gdbconf.environ)
        self.lmon = LMON_fe()
        try:
            self.lmon.init()
            self.lmon_session = self.lmon.createSession()
            self.lmon.putToBeDaemonEnv(self.lmon_session, gdbconf.environ.items())
            self.lmon.regPackForFeToBe(self.lmon_session, lmon.pack)
            self.lmon.regUnpackForBeToFe(self.lmon_session, lmon.unpack)
            if attach:
                self.lmon.attachAndSpawnDaemons(self.lmon_session,
                                                socket.getfqdn(),
                                                kwargs["pid"],
                                                gdbconf.backend_bin,
                                                gdbconf.backend_args,
                                                None, None)
            else:
                launcher_argv = [kwargs["launcher"]] + kwargs["launcher_args"]
                self.lmon.launchAndSpawnDaemons(self.lmon_session,
                                                socket.getfqdn(),
                                                kwargs["launcher"],
                                                launcher_argv,
                                                gdbconf.backend_bin,
                                                gdbconf.backend_args,
                                                None, None)
            self.proctab_size = self.lmon.getProctableSize(self.lmon_session)
            self.proctab, unused = self.lmon.getProctable(self.lmon_session, self.proctab_size)
        except lmon.LMONException as e:
            e.print_lmon_error()
            traceback.print_exc()
            return False
        # These are meaningless for the front-end.
        self.lmon_rank = None
        self.lmon_size = None
        self.lmon_master = None
        self._init_mpiranks()
        return True

    def _construct_mrnet_topology(self, comm_nodes = None):
        """Construct the topology to be used for MRNet.

        comm_nodes is a list of nodes to deploy comm nodes on. If none, the
        nodes are co-located on the same hosts as debuggers.

        """
        branch_factor = gdbconf.mrnet_branch_factor
        # Compute the minimum number of nodes we need given the branching factor.
        # This is the number of hosts LMON is deployed on, divided by the branching factor.
        lmon_hosts = list(set(map(lambda x: x.pd.host_name, self.proctab)))
        # Add 1 because this is integer division and we want the ceil.
        num_nodes = (len(lmon_hosts) / branch_factor) + 1
        host_list = comm_nodes
        if host_list:
            if len(host_list) < num_nodes:
                print "Not enough comm nodes: {0} < {1} (branch factor = {2})!".format(len(host_list), num_nodes, branch_factor)
                sys.exit(1)
        else:
            # We need to allocate comm nodes from among the back-end LMON hosts, so pick as many as needed.
            host_list = lmon_hosts[0:num_nodes]
        cur_host = socket.gethostname()
        if cur_host in host_list:
            print "Cannot have the front-end on the same machine as a back-end daemon."
            sys.exit(1)
        cur_parents = [cur_host]
        self.mrnet_topo_path = "{0}/topo_{1}".format(gdbconf.topology_path, os.getpid())
        fmt = "{0}:0"
        with open(self.mrnet_topo_path, "w+") as topo_file:
            while host_list:
                new_parents = []
                for parent in cur_parents:
                    children = host_list[:branch_factor]
                    new_parents += children
                    del host_list[:branch_factor]
                    if children:
                        topo_file.write(fmt.format(parent) + " => " +
                                        " ".join(map(lambda x: fmt.format(x), children)) + " ;\n")
                cur_parents = new_parents

    def _construct_local_node_topology(self):
        """Construct a topology for MRNet that just uses the local node."""
        cur_host = socket.gethostname()
        self.mrnet_topo_path = "{0}/topo_{1}".format(gdbconf.topology_path, os.getpid())
        with open(self.mrnet_topo_path, "w+") as topo_file:
            topo_file.write(cur_host + ":0 => " + cur_host + ":1 ;\n")

    def _assign_mrnet_leaves(self):
        """Assign debugger processes to MRNet leaves.

        For each leaf in the MRNet topology, assign up to the branching factor
        in debuggers for communication purposes.

        """
        topology = self.mrnet.get_NetworkTopology()
        # Note: This assumes that leaves gives us a list.
        mrnet_leaves = topology.get_Leaves()
        leaves = list(mrnet_leaves)
        num_nodes = topology.get_NumNodes() + 1 # Add 1 to make sure we're good.
        node_info = []
        local_rank = self.mrnet.get_LocalRank()
        leaf_idx = 0
        # be_rank is assigned to be greater than all the existing nodes.
        for i in range(0, len(self.get_lmon_hosts())):
            leaf = leaves[leaf_idx]
            # Check for root, since get_Parent fails on it.
            if leaf.get_Rank() == local_rank:
                node_info.append(NodeInfo(local_rank, leaf.get_HostName(),
                                          leaf.get_Port(), -1, num_nodes + i))
            else:
                node_info.append(NodeInfo(leaf.get_Rank(), leaf.get_HostName(),
                                          leaf.get_Port(), leaf.get_Parent(), num_nodes + i))
            if i % gdbconf.mrnet_branch_factor == (gdbconf.mrnet_branch_factor - 1):
                # Remove the leaf after we've given it mrnet_branch_factor children.
                leaf_idx += 1
        return node_info

    def _send_mrnet_topology(self):
        """Send the MRNet topology to the back-end daemons."""
        node_info = self._assign_mrnet_leaves()
        try:
            self.lmon.sendUsrDataBe(self.lmon_session, node_info)
        except lmon.LMONException as e:
            e.print_lmon_error()
            traceback.print_exc()
            return False
        self.mrnet_network_size = len(node_info)
        return True

    def _mrnet_node_joined_cb(self):
        """An MRNet callback invoked whenever a back-end node joins."""
        self.node_joins += 1

    def _mrnet_node_removed_cb(self):
        """An MRnet callback invoked whenever a back-end node leaves."""
        # TODO: Handle all nodes exiting.
        self.node_exits += 1

    def _wait_for_nodes(self):
        """Wait for all MRNet nodes to join the network."""
        while self.node_joins != self.mrnet_network_size: pass

    def _init_mrnet_streams(self):
        """Initialize basic MRNet streams."""
        self.broadcast_communicator = self.mrnet.get_BroadcastCommunicator()
        self.mrnet_broadcast_stream = self.mrnet.new_Stream(self.broadcast_communicator,
                                                            self.filter_ids[0],
                                                            MRN.SFILTER_WAITFORALL,
                                                            MRN.TFILTER_NULL)
        self.mrnet_frontend_stream = None # Not used here.

    def _send_mrnet_hello(self):
        """Send the HELLO message across MRNet."""
        self.send(GDBMessage(HELLO_MSG), self.broadcast)

    def _init_mrnet_rank_map(self):
        """Initialize the mappings from MPI ranks to MRNet ranks."""
        self.mpirank_to_mrnrank_map = {}
        hostname_to_mrnrank = {}
        mrnet_endpoints = self.broadcast_communicator.get_EndPoints()
        for endpoint in mrnet_endpoints:
            hostname_to_mrnrank[socket.getfqdn(endpoint.get_HostName())] = endpoint.get_Rank()
        for proc in self.get_proctab():
            self.mpirank_to_mrnrank_map[proc.mpirank] = hostname_to_mrnrank[socket.getfqdn(proc.pd.host_name)]

    def _load_mrnet_filters(self):
        """Load MRNet filters."""
        self.filter_ids = []
        for filter_path, filter_func in gdbconf.mrnet_filters:
            if os.path.isfile(filter_path):
                # Ensure the file actually still exists.
                try:
                    with open(filter_path):
                        ret_filter_id = self.mrnet.load_FilterFunc(filter_path, filter_func)
                        if ret_filter_id == -1:
                            print "Failed to load filter {0}:{1}!".format(filter_path, filter_func)
                            sys.exit(1)
                        self.filter_ids.append(ret_filter_id)
                except IOError:
                    print "Filter {0} disappeared!".format(filter_path)
                    sys.exit(1)
            else:
                print "Cannot find filter {0}!".format(filter_path)
                sys.exit(1)

    def init_mrnet(self, local = False):
        """Initialize MRNet.

        local is whether to initialize for a cluster or just this node.

        """
        if local:
            self._construct_local_node_topology()
        else:
            self._construct_mrnet_topology()
        self.mrnet = MRN.Network.CreateNetworkFE(self.mrnet_topo_path)
        self.node_joins = 0
        self.node_exits = 0
        self.mrnet.register_EventCallback(MRN.Event.TOPOLOGY_EVENT,
                                          MRN.TopologyEvent.TOPOL_ADD_BE,
                                          self._mrnet_node_joined_cb)
        self.mrnet.register_EventCallback(MRN.Event.TOPOLOGY_EVENT,
                                          MRN.TopologyEvent.TOPOL_REMOVE_NODE,
                                          self._mrnet_node_removed_cb)
        self._load_mrnet_filters()
        ret = self._send_mrnet_topology()
        if not ret:
            return False
        self._wait_for_nodes()
        self._init_shared_mrnet()
        self._enable_mrnet_perf_data()
        self._init_mrnet_rank_map()
        self._send_mrnet_hello()
        if gdbconf.mrnet_topology_dot:
            topo = self.mrnet.get_NetworkTopology()
            topo.print_DOTGraph(gdbconf.mrnet_topology_dot)
        return True

    def shutdown(self):
        """Shut down the communication infrastructure."""
        self._disable_mrnet_perf_data()
        self._log_mrnet_perf_data()
        # Shut this stream down.
        #del self.mrnet_broadcast_stream
        del self.mrnet
        try:
            self.lmon.shutdownDaemons(self.lmon_session)
        except lmon.LMONException as e:
            e.print_lmon_error()
            traceback.print_exc()
            return False
        self.been_shutdown = True
        return True

    def mpirank_to_mrnrank(self, rank):
        """Convert an MPI rank to an MRNet rank. Only works on front-end."""
        return self.mpirank_to_mrnrank_map[rank]

    def get_mrnet_network_size(self):
        """Return the size of the MRNet network."""
        return self.mrnet_network_size

    def get_exit_count(self):
        """Return the number of MRNet nodes that have exited."""
        return self.node_exits

    def all_nodes_exited(self):
        """Return whether all nodes have exited."""
        return self.node_exits == self.node_joins
