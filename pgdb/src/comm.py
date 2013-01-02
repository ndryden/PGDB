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

    def lmon_send(self):
        """Send data over LMon. Should be over-ridden by children."""
        raise NotImplemented

    def lmon_recv(self):
        """Receive data over LMon. Should be over-ridden by children."""
        raise NotImplemented

    def send(self, message, targets):
        """Send data over MRNet.
        
        message is the data to send.
        targets is an Interval of the targets to send the data to.

        """
        pass

    def recv(self, blocking = True):
        """Receive data over MRNet."""
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

    def _construct_mrnet_topology(self):
        """Construct the topology to be used for MRNet."""
        branch_factor = gdbconf.mrnet_branch_factor
        hostlist = list(set(map(lambda x: x.pd.host_name, self.proctab)))
        cur_host = socket.gethostname()
        if cur_host in hostlist:
            # The front-end cannot appear twice.
            print "Cannot have the front-end on the same machine as a back-end daemon."
            sys.exit(1)
        cur_parents = [cur_host] # Front end.
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

    def _send_mrnet_topology(self):
        """Send the MRNet topology to the back-end daemons."""
        topology = self.mrnet.get_NetworkTopology()
        leaves = topology.get_Leaves()
        parents = topology.get_ParentNodes()
        node_info = {}
        for leaf in leaves:
            node_info[leaf.get_Rank()] = NodeInfo(leaf.get_Rank(),
                                                  leaf.get_HostName(),
                                                  leaf.get_Port(),
                                                  leaf.get_Parent())
        local_rank = self.mrnet.get_LocalRank()
        for parent in parents:
            if parent.get_Rank() != local_rank:
                node_info[parent.get_Rank()] = NodeInfo(parent.get_Rank(),
                                                        parent.get_HostName(),
                                                        parent.get_Port(),
                                                        parent.get_Parent())
            else:
                # Special case for root as calling parent.get_Rank() on the root segfaults.
                node_info[local_rank] = NodeInfo(local_rank, parent.get_HostName(),
                                                 parent.get_Port(), -1)
        self.lmon_send(node_info)
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
