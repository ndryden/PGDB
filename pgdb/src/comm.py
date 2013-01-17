"""Primary communication class for managing LaunchMON and MRNet communication."""

import cPickle, os, sys, socket
from conf import gdbconf
from lmon import lmon
from lmon.lmonfe import LMON_fe
from lmon.lmonbe import LMON_be
from MRNet import MRN, shared_ptr

class Communicator (object):
    """Basic communicator class."""

    def __init__(self):
        """Initialize things."""
        self.lmon = None
        self.mrnet = None

    def init_lmon(self):
        """Initialize LaunchMON. Should be over-ridden by children."""
        raise NotImplemented

    def init_mrnet(self):
        """Initialize MRNet. Should be over-ridden by children."""
        raise NotImplemented

    def get_proctab_size(self):
        """Return the size of the process table from LaunchMON"""
        return self.proctab_size

    def get_proctab(self):
        """Return the process table from LaunchMON."""
        return self.proctab

    def get_lmon_hosts(self):
        """Return the set of hosts on which LaunchMON runs."""
        return list(set(map(lambda x: x.pd.host_name, self.proctab)))

    def send(self, message, targets):
        """Send data over MRNet.

        message is the data to send.
        targets is an Interval of the targets to send the data to.

        """
        pass

    def recv(self, blocking = True):
        """Receive data over MRNet."""
        pass

class CommunicatorBE (Communicator):
    """Communicator for the back-end."""

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

    def init_mrnet(self):
        """Initialize MRNet."""
        local_node_info = None
        if self.lmon_master:
            # Receive topology information from front-end.
            node_info = self.lmon.recvUsrData(gdbconf.topology_transmit_size)
            # Scatter topology information to back-end.
            # Presently uses a node info size of 256.
            local_node_info = self.lmon.scatter(node_info.items(), 256)
        else:
            # Receive scattered topology.
            local_node_info = self.lmon.scatter(None, 256)
        # Construct MRNet arguments and create network.
        argv = [sys.argv[0], # Program name.
                str(local_node_info.host), # Comm node host.
                str(local_node_info.port), # Comm node port.
                str(local_node_info.mrnrank), # Comm node rank.
                socket.getfqdn(), # My host.
                str(local_node_info.be_rank)] # My rank.
        # Initialize.
        self.mrnet = MRN.Network.CreateNetworkBE(6, argv)
        self.packet_stash = []

    def send(self, message, targets):
        pass

    def recv(self, blocking = True):
        pass

class CommunicatorFE (Communicator):
    """Communicator for the front-end."""

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
            while hostlist:
                new_parents = []
                for parent in cur_parents:
                    children = hostlist[:branch_factor]
                    new_parents += children
                    del hostlist[:branch_factor]
                    if children:
                        topo_file.write(fmt.format(parent) + " => " +
                                        " ".join(map(lambda x: fmt.format(x), children)) + " ;\n")
                cur_parents = new_parents

    def _assign_mrnet_leaves(self):
        """Assign debugger processes to MRNet leaves.

        For each leaf in the MRNet topology, assign up to the branching factor
        in debuggers for communication purposes.

        """
        topology = self.mrnet.get_NetworkTopology()
        # Note: This assumes that leaves gives us a list.
        leaves = topology.get_Leaves()
        num_nodes = topology.get_NumNodes() + 1 # Add 1 to make sure we're good.
        node_info = []
        local_rank = self.mrnet.get_LocalRank()
        # be_rank is assigned to be greater than all the existing nodes.
        for i in range(0, len(self.get_lmon_hosts())):
            leaf = leaves[0]
            # Check for root, since get_Parent fails on it.
            if leaf.get_Rank() == local_rank:
                node_info.append(NodeInfo(local_rank, leaf.get_HostName(),
                                          leaf.get_Port(), -1, num_nodes + i))
            else:
                node_info.append(NodeInfo(leaf.get_Rank(), leaf.get_HostName(),
                                          leaf.get_Port(), leaf.get_Parent()), num_nodes + i)
            if i % gdbconf.mrnet_branch_factor == (gdbconf.mrnet_branch_factor - 1):
                # Remove the leaf after we've given it mrnet_branch_factor children.
                leaves.pop(0)
        return node_info

    def _send_mrnet_topology(self):
        """Send the MRNet topology to the back-end daemons."""
        node_info = self._assign_mrnet_leaves()
        self.lmon.sendUsrDataBe(self.lmon_session, node_info)
        self.mrnet_network_size = len(node_info) - 1

    def _init_mrnet_streams(self):
        """Initialize MRNet streams."""
        self.mrnet_broadcast_comm = self.mrnet.get_BroadcastCommunicator()

    def _construct_mrnet_rank_mapping(self):
        """Create a mapping from MRNet ranks to MPI ranks."""
        self.mpirank_to_mrnrank = {}
        self.mpiranks = []
        hostname_to_mrnrank = {}
        for ep in self.

    def init_mrnet(self):
        """Initialize MRNet."""
        self._construct_mrnet_topology()
        self.mrnet = MRN.Network.CreateNetworkFE(self.mrnet_topo_path)
        self.mrnet.register_EventCallback(MRN.Event.TOPOLOGY_EVENT,
                                          MRN.TopologyEvent.TOPOL_ADD_BE,
                                          self.mrnet_node_joined_cb)
        self.mrnet.register_EventCallback(MRN.Event.TOPOLOGY_EVENT,
                                          MRN.TopologyEvent.TOPOL_REMOVE_NODE,
                                          self.mrnet_node_removed_cb)
        self._send_mrnet_topology()
