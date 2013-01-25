"""Primary communication class for managing LaunchMON and MRNet communication."""

import cPickle, os, sys, socket, threading
from gdb_shared import *
from conf import gdbconf
from lmon import lmon
from lmon.lmonfe import LMON_fe
from lmon.lmonbe import LMON_be
from MRNet import MRN, shared_ptr

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
        self.packet_stash = []
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

    def mpirank_to_mrnrank(self, rank):
        """Convert an MPI rank to an MRNet rank. Only works on front-end."""
        return self.mpirank_to_mrnrank_map[rank]

    def _multi_payload_split(self, msg):
        """Given a message, split it into multi-messages if needed."""
        if len(msg) > gdbconf.multi_len:
            split_len = gdbconf.multi_len
            payloads = [msg[i:i + split_len] for i in range(0, len(msg), split_len)]
            payload_msgs = [GDBMessage(MULTI_MESSAGE, num = len(payloads))]
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
            stream = None
            mrnet_ranks = []
            for rank in interval.members():
                mrnet_ranks.append(self.mpirank_to_mrnrank(rank))
            # Since multiple MPI ranks correspond to one MRNet rank, eliminate duplicates.
            mrnet_ranks = list(set(mrnet_ranks))
            comm = self.mrnet.new_Communicator(mrnet_ranks)
            return self.mrnet.new_Stream(comm, 0, 0, 0)

    def send(self, message, targets):
        """Send data over MRNet.

        message is the GDBMessage to send.
        targets is an Interval of the targets to send the data to, or one of
        self.frontend or self.broadcast.

        """
        msg = cPickle.dumps(message, 0)
        self._lock()
        send_list = self._multi_payload_split(msg)
        stream = self._get_stream_for_interval(targets)
        for payload in send_list:
            if stream.send(MSG_TAG, "%s", payload) == -1:
                print "Fatal error on stream send."
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
        ret, serialized = packet.get.unpack("%s")
        if ret == -1:
            print "Could not unpack packet."
            sys.exit(1)
        msg = cPickle.loads(serialized)
        # This keeps Python from garbage-collecting these.
        self.packet_stash.append(packet)
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
        if self.lmon_master:
            # Receive topology information from front-end.
            node_info = self.lmon.recvUsrData(gdbconf.topology_transmit_size)
            # Scatter topology information to back-end.
            # Presently uses a node info size of 256.
            local_node_info = self.lmon.scatter(node_info, 256)
        else:
            # Receive scattered topology.
            local_node_info = self.lmon.scatter(None, 256)
        # Construct MRNet arguments and create network.
        argv= [sys.argv[0], # Program name.
                str(local_node_info.host), # Comm node host.
                str(local_node_info.port), # Comm node port.
                str(local_node_info.mrnrank), # Comm node rank.
                socket.getfqdn(), # My host.
                str(local_node_info.be_rank)] # My rank.
        # Initialize.
        self.mrnet = MRN.Network.CreateNetworkBE(6, argv)
        self._init_shared_mrnet()
        self._wait_for_hello()

    def shutdown(self):
        """Shut down the communication infrastructure."""
        self.lmon.finalize()
        self.mrnet.waitfor_ShutDown()
        del self.mrnet
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
        # These are meaningless for the front-end.
        self.lmon_rank = None
        self.lmon_size = None
        self.lmon_master = None

    def _construct_mrnet_topology(self, comm_nodes = None):
        """Construct the topology to be used for MRNet.

        comm_nodes is a list of nodes to deploy comm nodes on. If none, the
        nodes are co-located on the same hosts as debuggers.

        """
        branch_factor = gdbconf.mrnet_branch_factor
        host_list = comm_nodes
        if not host_list:
            host_list = list(set(map(lambda x: x.pd.host_name, self.proctab)))
        cur_host = socket.gethostname()
        if cur_host in host_list:
            print "Cannot have the front-end on the same machine as a pack-end daemon."
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

    def _assign_mrnet_leaves(self):
        """Assign debugger processes to MRNet leaves.

        For each leaf in the MRNet topology, assign up to the branching factor
        in debuggers for communication purposes.

        """
        self.topology = self.mrnet.get_NetworkTopology()
        # Note: This assumes that leaves gives us a list.
        self.mrnet_leaves = self.topology.get_Leaves()
        leaves = list(self.mrnet_leaves)
        num_nodes = self.topology.get_NumNodes() + 1 # Add 1 to make sure we're good.
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
        self.lmon.sendUsrDataBe(self.lmon_session, node_info)
        self.mrnet_network_size = len(node_info)

    def _mrnet_node_joined_cb(self):
        """An MRNet callback invoked whenever a back-end node joins."""
        self.node_joins += 1

    def _mrnet_node_removed_cb(self):
        """An MRnet callback invoked whenever a back-end node leaves."""
        # TODO: Handle all nodes exiting.
        pass

    def _wait_for_nodes(self):
        """Wait for all MRNet nodes to join the network."""
        while self.node_joins != self.mrnet_network_size: pass

    def _init_mrnet_streams(self):
        """Initialize basic MRNet streams."""
        self.broadcast_communicator = self.mrnet.get_BroadcastCommunicator()
        self.mrnet_broadcast_stream = self.mrnet.new_Stream(self.broadcast_communicator, 0, 0, 0)
        self.mrnet_frontend_stream = None # Not used here.

    def _send_mrnet_hello(self):
        """Send the HELLO message across MRNet."""
        self.send(GDBMessage(HELLO_MSG), self.broadcast)

    def _init_mrnet_rank_map(self):
        """Initialize the mappings from MPI ranks to MRNet ranks."""
        self.mpirank_to_mrnrank_map = {}
        hostname_to_mrnrank = {}
        self.mrnet_endpoints = self.broadcast_communicator.get_EndPoints()
        for endpoint in self.mrnet_endpoints:
            hostname_to_mrnrank[socket.getfqdn(endpoint.get_HostName())] = endpoint.get_Rank()
        for proc in self.get_proctab():
            self.mpirank_to_mrnrank_map[proc.mpirank] = hostname_to_mrnrank[socket.getfqdn(proc.pd.host_name)]

    def init_mrnet(self):
        """Initialize MRNet."""
        self._construct_mrnet_topology()
        self.mrnet = MRN.Network.CreateNetworkFE(self.mrnet_topo_path)
        self.node_joins = 0
        self.mrnet.register_EventCallback(MRN.Event.TOPOLOGY_EVENT,
                                          MRN.TopologyEvent.TOPOL_ADD_BE,
                                          self._mrnet_node_joined_cb)
        self.mrnet.register_EventCallback(MRN.Event.TOPOLOGY_EVENT,
                                          MRN.TopologyEvent.TOPOL_REMOVE_NODE,
                                          self._mrnet_node_removed_cb)
        self._send_mrnet_topology()
        self._wait_for_nodes()
        self._init_shared_mrnet()
        self._init_mrnet_rank_map()
        self._send_mrnet_hello()

    def shutdown(self):
        """Shut down the communication infrastructure."""
        del self.mrnet
        self.been_shutdown = True
