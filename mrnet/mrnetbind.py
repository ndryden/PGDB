from pybindgen import *
from pybindgen.typehandlers.base import PointerParameter, ReverseWrapperBase, ForwardWrapperBase
from pybindgen.typehandlers import inttype
import sys

class CharStarStarParam(PointerParameter):
    DIRECTIONS = [Parameter.DIRECTION_IN, Parameter.DIRECTION_OUT]
    CTYPES = ["char**"]

    def convert_c_to_python(self, wrapper):
        raise NotImplementedError

    def convert_python_to_c(self, wrapper):
        assert isinstance(wrapper, ForwardWrapperBase)
        if self.direction & self.DIRECTION_IN:
            if self.default_value is None:
                tmp_name = wrapper.declarations.declare_variable("PyObject*", "_" + self.name)
                name = wrapper.declarations.declare_variable(self.ctype_no_const, self.name)
                wrapper.parse_params.add_parameter("O", ["&" + tmp_name], self.value)
                wrapper.before_call.write_code("{0} = layout_argv({1});".format(name, tmp_name))
                wrapper.before_call.write_code("if (!{0}) return NULL;".format(name))
                wrapper.after_call.write_code("layout_argv_cleanup({0});".format(name));
            elif self.default_value == "NULL":
                name = wrapper.declarations.declare_variable(self.ctype_no_const, self.name, "NULL")
            else:
                raise NotImplementedError
            if ("const" in self.ctype):
                # This is horrible practice.
                wrapper.call_params.append("(const char**) " + name)
            else:
                wrapper.call_params.append(name)
        else:
            name = wrapper.declarations.declare_variable("char*", self.name)
            wrapper.call_params.append("&" + name)
            wrapper.build_params.add_parameter("s", [name])

class EventCallbackParam(Parameter):
    DIRECTIONS = [Parameter.DIRECTION_IN]
    CTYPES = ['evt_cb_func']

    def convert_c_to_python(self, wrapper):
        raise NotImplementedError

    def convert_python_to_c(self, wrapper):
        assert isinstance(wrapper, ForwardWrapperBase)
        cb = wrapper.declarations.declare_variable("PyObject*", self.name)
        wrapper.parse_params.add_parameter("O", ["&" + cb], self.value)
        wrapper.before_call.write_error_check("!PyCallable_Check({0})".format(cb),
                                              'PyErr_SetString(PyExc_TypeError, "Callback parameter must be callable.");')
        wrapper.call_params.append("&_wrap_EventCallback")
        wrapper.before_call.write_code("Py_INCREF({0});".format(cb))
        #wrapper.before_call.add_cleanup_code("Py_DECREF({0});".format(cb))
        # We cannot delete this reference here! At present, we leak this memory if the callback is removed.
        wrapper.call_params.append(cb)

#class UIntRefParam(inttype.UnsignedIntParam):
#    DIRECTIONS = [Parameter.DIRECTION_IN, Parameter.DIRECTION_OUT,
#                  Parameter.DIRECTION_IN | Parameter.DIRECTION_OUT]
#    CTYPES = ["unsigned int&", "uint32_t&"]
#
#    def convert_c_to_python(self, wrapper):
#        assert isinstance(wrapper, ReverseWrapperBase)
#        if self.direction & self.DIRECTION_IN:
#            wrapper.build_params.add_parameter("I", [self.value])
#        if self.direction & self.DIRECTION_OUT:
#            wrapper.build_params.add_parameter("I", [self.value], self.name)
#
#    def convert_python_to_c(self, wrapper):
#        assert isinstance(wrapper, ForwardWrapperBase)
#        name = wrapper.declarations.declare_variable(self.ctype_no_const[:-1], self.name)
#        wrapper.call_params.append(name)
#        if self.direction & self.DIRECTION_IN:
#            wrapper.parse_params.add_parameter("I", ["&" + name], self.name)
#        if self.direction & self.DIRECTION_OUT:
#            wrapper.build_params.add_parameter("I", [name])

class StreamStarStar(PointerParameter):
    DIRECTIONS = [Parameter.DIRECTION_OUT]
    CTYPES = ["Stream**"]

    def convert_c_to_python(self, wrapper):
        assert isinstance(wrapper, ReverseWrapperBase)
        raise NotImplementedError

    def convert_python_to_c(self, wrapper):
        assert isinstance(wrapper, ForwardWrapperBase)
        # Note: These typenames are hardcoded and could break if PyBindGen changes.
        name = wrapper.declarations.declare_variable("PyMRNStream*", self.name)
        wrapper.before_call.write_code(name + " = PyObject_New(PyMRNStream, &PyMRNStream_Type);")
        wrapper.call_params.append("&(" + name + "->obj)")
        wrapper.build_params.add_parameter("N", [name])
        wrapper.after_call.write_code("if (!" + name + ') {\n\treturn Py_BuildValue((char*) "iOOO", retval, Py_None, Py_None, Py_None);\n}')
        # This should keep Python from garbage-collecting this.
        wrapper.after_call.write_code("Py_INCREF(" + name + ");")

mod = Module("MRNet")
mod.add_include('"mrnet/MRNet.h"')
mod.add_include('"mrnetbind.h"')
MRN = mod.add_cpp_namespace("MRN")
CommunicationNode = MRN.add_class("CommunicationNode")
Communicator = MRN.add_class("Communicator")
Error = MRN.add_class("Error")
Event = MRN.add_class("Event")
DataEvent = MRN.add_class("DataEvent", parent = Event)
ErrorEvent = MRN.add_class("ErrorEvent", parent = Event)
TopologyEvent = MRN.add_class("TopologyEvent", parent = Event)
NetworkTopology = MRN.add_class("NetworkTopology", parent = Error)
Node = NetworkTopology.add_class("Node")
Packet = MRN.add_class("Packet", parent = Error)
Stream = MRN.add_class("Stream")
Network = MRN.add_class("Network", parent = Error)
packet_ptr = mod.add_class("boost::shared_ptr", template_parameters = ["MRN::Packet"], custom_name = "shared_ptr")

# Simple utility types.
#MRN.add_class("Port") # Port is a uint16_t.
#MRN.add_class("Rank") # Rank is a uint32_t.
# These are both ints.
#MRN.add_class("EventClass")
#MRN.add_class("EventType")
MRN.add_class("EventData")

mod.add_container("std::map<std::string, std::string>", ("std::string", "std::string"), "map")
mod.add_container("std::set<MRN::CommunicationNode*>", retval("MRN::CommunicationNode*", caller_owns_return = False, reference_existing_object = True), "set")
mod.add_container("std::set<MRN::NetworkTopology::Node*>", retval("MRN::NetworkTopology::Node*", caller_owns_return = False, reference_existing_object = True), "set")
mod.add_container("std::vector<MRN::NetworkTopology::Node*>", retval("MRN::NetworkTopology::Node*", caller_owns_return = False, reference_existing_object = True), "vector")
mod.add_container("std::set<uint32_t>", "uint32_t", "set")
#mod.add_container("std::vector<const char*>", retval("const char*", caller_owns_return = True), "vector")
mod.add_container("std::vector<int>", "int", "vector")

# Set up packet_ptr.
packet_ptr.add_constructor([])
packet_ptr.add_constructor([param("MRN::Packet*", "packet", transfer_ownership = True)])
packet_ptr.add_method("get", retval("MRN::Packet*",
                                    caller_owns_return = False,
                                    reference_existing_object = True),
                      [], is_const = True)

# Set up CommunicationNode.
CommunicationNode.add_method("get_HostName", retval("std::string"), [], is_const = True)
CommunicationNode.add_method("get_Port", retval("uint16_t"), [], is_const = True)
CommunicationNode.add_method("get_Rank", retval("uint32_t"), [], is_const = True)

# Set up Communicator.
Communicator.add_method("add_EndPoint", retval("bool"), [param("uint32_t", "irank")])
Communicator.add_method("add_EndPoint", retval("bool"), [param("MRN::CommunicationNode*", "node", transfer_ownership = False)])
# Note: This is not actually the right return type, but references don't really work here.
Communicator.add_method("get_EndPoints", retval("const std::set<MRN::CommunicationNode*>"), [], is_const = True)
Communicator.add_method("size", retval("unsigned int"), [], is_const = True)

# Set up Error.
MRN.add_enum("ErrorLevel", ["ERR_INFO", "ERR_WARN", "ERR_ERR", "ERR_CRIT", "ERR_LEVEL_LAST"])
MRN.add_enum("ErrorResponse", ["ERR_IGNORE", "ERR_ALERT", "ERR_RETRY", "ERR_ABORT", "ERR_RESPONSE_LAST"])
MRN.add_enum("ErrorCode", ["ERR_NONE", "ERR_TOPOLOGY_FORMAT", "ERR_TOPOLOGY_CYCLE", "ERR_TOPOLOGY_NOTCONNECTED",
                           "ERR_NETWORK_FAILURE", "ERR_FORMATSTR", "ERR_PACKING", "ERR_INTERNAL", "ERR_SYSTEM",
                           "ERR_CODE_LAST"])
ErrorDef = MRN.add_struct("ErrorDef")
ErrorDef.add_instance_attribute("code", "ErrorCode")
ErrorDef.add_instance_attribute("level", "ErrorLevel")
ErrorDef.add_instance_attribute("response", "ErrorResponse")
ErrorDef.add_instance_attribute("msg", "const char*")
Error.add_method("has_Error", retval("bool"), [], is_const = True)
Error.add_method("get_Error", retval("MRN::ErrorCode"), [], is_const = True)
Error.add_method("get_ErrorStr", retval("const char*", caller_owns_return = False),
                 [param("MRN::ErrorCode", "err")],
                 is_const = True)

# Set up Event.
Event.add_method("get_Class", retval("int"), [], is_const = True)
Event.add_method("get_Type", retval("int"), [], is_const = True)
Event.add_method("get_Data", retval("MRN::EventData*",
                                    caller_owns_return = False,
                                    reference_existing_object = True), [], is_const = True)
Event.add_static_attribute("EVENT_CLASS_ALL", "int")
Event.add_static_attribute("DATA_EVENT", "int")
Event.add_static_attribute("TOPOLOGY_EVENT", "int")
Event.add_static_attribute("ERROR_EVENT", "int")
DataEvent.add_static_attribute("DATA_AVAILABLE", "int")
ErrorEvent.add_static_attribute("ERROR_INTERNAL", "int")
ErrorEvent.add_static_attribute("ERROR_SYSTEM", "int")
ErrorEvent.add_static_attribute("ERROR_USAGE", "int")
TopologyEvent.add_static_attribute("TOPOL_ADD_BE", "int")
TopologyEvent.add_static_attribute("TOPOL_ADD_CP", "int")
TopologyEvent.add_static_attribute("TOPOL_REMOVE_NODE", "int")
TopologyEvent.add_static_attribute("TOPOL_CHANGE_PARENT", "int")

# Set up Node.
Node.add_method("get_HostName", retval("std::string"), [], is_const = True)
Node.add_method("get_Port", retval("uint16_t"), [], is_const = True)
Node.add_method("get_Rank", retval("uint32_t"), [], is_const = True)
Node.add_method("get_Parent", retval("uint32_t"), [], is_const = True)
# Note: This should return a reference.
Node.add_method("get_Children", retval("const std::set<MRN::NetworkTopology::Node*>"), [], is_const = True)
Node.add_method("get_NumChildren", retval("unsigned int"), [], is_const = True)
Node.add_method("find_SubTreeHeight", retval("unsigned int"), [])

# Set up NetworkTopology.
NetworkTopology.add_method("print_TopologyFile", retval("void"),
                           [param("const char*", "filename", transfer_ownership = False)],
                           is_const = True)
NetworkTopology.add_method("print_DOTGraph", retval("void"),
                           [param("const char*", "filename", transfer_ownership = False)],
                           is_const = True)
# We do not implement print because we would have to deal with FILE.
NetworkTopology.add_method("get_NumNodes", retval("unsigned int"), [], is_const = True)
NetworkTopology.add_method("get_TreeStatistics", retval("void"),
                           [param("unsigned int&", "onum_nodes", direction = Parameter.DIRECTION_OUT),
                            param("unsigned int&", "odepth", direction = Parameter.DIRECTION_OUT),
                            param("unsigned int&", "omin_fanout", direction = Parameter.DIRECTION_OUT),
                            param("unsigned int&", "omax_fanout", direction = Parameter.DIRECTION_OUT),
                            param("double&", "oavg_fanout", direction = Parameter.DIRECTION_OUT),
                            param("double&", "ostddev_fanout", direction = Parameter.DIRECTION_OUT)])
NetworkTopology.add_method("get_Root", retval("MRN::NetworkTopology::Node*",
                                              caller_owns_return = False,
                                              reference_existing_object = True),
                           [], is_const = True)
NetworkTopology.add_method("find_Node", retval("MRN::NetworkTopology::Node*",
                                               caller_owns_return = False,
                                               reference_existing_object = True),
                           [param("uint32_t", "rank")],
                           is_const = True)
NetworkTopology.add_method("get_Leaves", retval("void"),
                           [param("std::vector<MRN::NetworkTopology::Node*>&", "leaves", direction = Parameter.DIRECTION_OUT)],
                           is_const = True)
NetworkTopology.add_method("get_ParentNodes", retval("void"),
                           [param("std::set<MRN::NetworkTopology::Node*>&", "set", direction = Parameter.DIRECTION_OUT)],
                           is_const = True)
NetworkTopology.add_method("get_OrphanNodes", retval("void"),
                           [param("std::set<MRN::NetworkTopology::Node*>&", "set", direction = Parameter.DIRECTION_OUT)],
                           is_const = True)
NetworkTopology.add_method("get_BackEndNodes", retval("void"),
                           [param("std::set<MRN::NetworkTopology::Node*>&", "set", direction = Parameter.DIRECTION_OUT)],
                           is_const = True)

# Set up Packet.
# Note: Variadic support in Python.
Packet.add_method("unpack", retval("int"),
                  [param("const char*", "ifmt", transfer_ownership = False),
                   param("const char**", "serialized", transfer_ownership = False, direction = Parameter.DIRECTION_OUT)])
# TODO: Overloaded operator[].
Packet.add_method("get_Tag", retval("int"), [], is_const = True)
Packet.add_method("set_Tag", retval("void"),
                  [param("int", "itag")])
Packet.add_method("get_StreamId", retval("int"), [], is_const = True)
Packet.add_method("set_StreamId", retval("void"),
                  [param("unsigned int", "istream_id")])
Packet.add_method("get_FormatString", retval("const char*", caller_owns_return = False), [], is_const = True)
Packet.add_method("get_InletNodeRank", retval("uint32_t"), [], is_const = True)
Packet.add_method("get_SourceRank", retval("uint32_t"), [], is_const = True)
Packet.add_method("set_Destinations", retval("bool"),
                  [param("const uint32_t*", "bes", transfer_ownership = False),
                   param("unsigned int", "num_bes")])
Packet.add_method("set_DestroyData", retval("void"),
                  [param("bool", "b")])
Packet.add_binary_comparison_operator("==")
Packet.add_binary_comparison_operator("!=")

# Set up Stream.
# No TFILTER_EPK_UNIFY, causes undefined symbol errors.
MRN.add_enum("FilterId", ["TFILTER_NULL", "TFILTER_SUM", "TFILTER_AVG", "TFILTER_MIN",
                          "TFILTER_MAX", "TFILTER_ARRAY_CONCAT", "TFILTER_INT_EQ_CLASS",
                          "TFILTER_PERFDATA", "TFILTER_TOPO_UPDATE",
                          "TFILTER_TOPO_UPDATE_DOWNSTREAM",
                          "SFILTER_DONTWAIT", "SFILTER_WAITFORALL", "SFILTER_TIMEOUT"])
MRN.add_enum("FilterType", ["FILTER_DOWNSTREAM_TRANS", "FILTER_UPSTREAM_TRANS", "FILTER_UPSTREAM_SYNC"])
Stream.add_method("send", retval("int"),
                  [param("int", "itag"),
                   param("const char*", "format_string", transfer_ownership = False),
                   param("const char*", "serialized", transfer_ownership = False)])
Stream.add_method("flush", retval("int"), [], is_const = True)
Stream.add_method("recv", retval("int"),
                  [param("int*", "otag", transfer_ownership = False, direction = Parameter.DIRECTION_OUT),
                   param("boost::shared_ptr<MRN::Packet>&", "opacket", direction = Parameter.DIRECTION_OUT),
                   param("bool", "iblocking", default_value = "true")])
Stream.add_method("get_EndPoints", retval("const std::set<uint32_t>"), [], is_const = True)
Stream.add_method("get_Id", retval("unsigned int"), [], is_const = True)
Stream.add_method("size", retval("unsigned int"), [], is_const = True)
Stream.add_method("has_Data", retval("bool"), [])
Stream.add_method("get_DataNotificationFd", retval("int"), [])
Stream.add_method("clear_DataNotificationFd", retval("void"), [])
Stream.add_method("close_DataNotificationFd", retval("void"), [])
# TODO: set_FilterParameters: variadic version.
Stream.add_method("set_FilterParameters", retval("int"),
                  [param("MRN::FilterType", "ftype"),
                   param("const char*", "format", transfer_ownership = False),
                   param("int", "val")])
# TODO: PerformanceData functions.
Stream.add_method("is_Closed", retval("bool"), [], is_const = True)

# Set up Network.
Network.add_method("CreateNetworkFE", retval("MRN::Network*", caller_owns_return = True),
                   [param("const char*", "topology", transfer_ownership = False),
                    param("const char*", "backend_exe", transfer_ownership = False),
                    param("const char**", "backend_argv", transfer_ownership = False),
                    param("std::map<std::string, std::string>*", "attrs", transfer_ownership = False),
                    param("bool", "rank_backends", default_value = "true"),
                    param("bool", "using_memory_buffer", default_value = "false")],
                   is_static = True)
Network.add_method("CreateNetworkFE", retval("MRN::Network*", caller_owns_return = True),
                   [param("const char*", "topology", transfer_ownership = False),
                    param("const char*", "backend_exe", transfer_ownership = False, default_value = "NULL"),
                    param("const char**", "backend_argv", transfer_ownership = False, default_value = "NULL")],
                   is_static = True)
Network.add_method("CreateNetworkFE", retval("MRN::Network*", caller_owns_return = True),
                   [param("const char*", "topology", transfer_ownership = False),
                    param("const char*", "backend_exe", transfer_ownership = False),
                    param("const char**", "backend_argv", transfer_ownership = False)],
                   is_static = True)
Network.add_method("CreateNetworkBE", retval("MRN::Network*", caller_owns_return = True),
                   [param("int", "argc"),
                    param("char**", "argv", transfer_ownership = False)],
                   is_static = True)
Network.add_method("get_NetworkTopology", retval("MRN::NetworkTopology*",
                                                 caller_owns_return = False,
                                                 reference_existing_object = True),
                   [], is_const = True)
Network.add_method("is_ShutDown", retval("bool"), [], is_const = True)
Network.add_method("waitfor_ShutDown", retval("void"), [], is_const = True)
Network.add_method("print_error", retval("void"),
                   [param("const char*", "msg", transfer_ownership = False)])
Network.add_method("get_LocalHostName", retval("std::string"), [], is_const = True)
Network.add_method("get_LocalPort", retval("uint16_t"), [], is_const = True)
Network.add_method("get_LocalRank", retval("uint32_t"), [], is_const = True)
Network.add_method("is_LocalNodeChild", retval("bool"), [], is_const = True)
Network.add_method("is_LocalNodeParent", retval("bool"), [], is_const = True)
Network.add_method("is_LocalNodeInternal", retval("bool"), [], is_const = True)
Network.add_method("is_LocalNodeFrontEnd", retval("bool"), [], is_const = True)
Network.add_method("is_LocalNodeBackEnd", retval("bool"), [], is_const = True)
Network.add_method("get_BroadcastCommunicator", retval("MRN::Communicator*",
                                                       caller_owns_return = False,
                                                       reference_existing_object = True),
                   [], is_const = True)
# Note: I am unsure of the correct ownership tranfer for the new_Communicator functions.
Network.add_method("new_Communicator", retval("MRN::Communicator*",
                                              caller_owns_return = False,
                                              reference_existing_object = True)
                   , [])
Network.add_method("new_Communicator", retval("MRN::Communicator*",
                                              caller_owns_return = False,
                                              reference_existing_object = True),
                   [param("Communicator&", "communicator")])
Network.add_method("new_Communicator", retval("MRN::Communicator*",
                                              caller_owns_return = False,
                                              reference_existing_object = True),
                   [param("const std::set<uint32_t>&", "set")])
Network.add_method("new_Communicator", retval("MRN::Communicator*",
                                              caller_owns_return = False,
                                              reference_existing_object = True),
                   [param("std::set<MRN::CommunicationNode*>&", "set")])
Network.add_method("get_EndPoint", retval("MRN::CommunicationNode*",
                                          caller_owns_return = False,
                                          reference_existing_object = True),
                   [param("uint32_t", "rank")],
                   is_const = True)
Network.add_method("load_FilterFunc", retval("int"),
                   [param("const char*", "so_file", transfer_ownership = False),
                    param("const char*", "func", transfer_ownership = False)])
#Network.add_method("load_FilterFuncs", retval("int"),
#                   [param("const char*", "so_file", transfer_ownership = False),
#                    param("const std::vector<const char*>", "functions"),
#                    param("std::vector<int>", "filter_ids")])
# TODO: Filter IDs and default values.
Network.add_method("new_Stream", retval("MRN::Stream*",
                                        caller_owns_return = False,
                                        reference_existing_object = True),
                   [param("Communicator*", "communicator", transfer_ownership = False),
                    param("int", "us_filter_id"),
                    param("int", "sync_id"),
                    param("int", "ds_filter_id")])
Network.add_method("new_Stream", retval("MRN::Stream*",
                                        caller_owns_return = False,
                                        reference_existing_object = True),
                   [param("Communicator*", "communicator", transfer_ownership = False),
                    param("std::string", "us_filters"),
                    param("std::string", "sync_filters"),
                    param("std::string", "ds_filters")])
Network.add_method("get_Stream", retval("MRN::Stream*",
                                        caller_owns_return = False,
                                        reference_existing_object = True),
                   [param("unsigned int", "iid")],
                   is_const = True)
Network.add_method("recv", retval("int"),
                   [param("int*", "otag", transfer_ownership = False, direction = Parameter.DIRECTION_OUT),
                    param("boost::shared_ptr<MRN::Packet>&", "opacket", direction = Parameter.DIRECTION_OUT),
                    param("Stream**", "ostream", transfer_ownership = False, direction = Parameter.DIRECTION_OUT),
                    param("bool", "iblocking", default_value = "true", direction = Parameter.DIRECTION_IN)])
Network.add_method("send", retval("int"),
                   [param("uint32_t", "ibe"),
                    param("int", "tag"),
                    param("const char*", "iformat_str", transfer_ownership = False),
                    param("const char*", "serialized", transfer_ownership = False)])
Network.add_method("flush", retval("int"), [], is_const = True)
MRN.add_enum("perfdata_metric_t", ["PERFDATA_MET_NUM_BYTES", "PERFDATA_MET_NUM_PKTS", "PERFDATA_MET_ELAPSED_SEC",
                                   "PERFDATA_MET_CPU_SYS_PCT", "PERFDATA_MET_CPU_USR_PCT",
                                   "PERFDATA_MET_MEM_VIRT_KB", "PERFDATA_MET_MEM_PHYS_KB",
                                   "PERFDATA_MAX_MET"])
MRN.add_enum("perfdata_context_t", ["PERFDATA_CTX_NONE", "PERFDATA_CTX_SEND", "PERFDATA_CTX_RECV",
                                    "PERFDATA_CTX_FILT_IN", "PERFDATA_CTX_FILT_OUT", "PERFDATA_CTX_SYNCFILT_IN",
                                    "PERFDATA_CTX_SYNCFILT_OUT", "PERFDATA_CTX_PKT_RECV", "PERFDATA_CTX_PKT_SEND",
                                    "PERFDATA_CTX_PKT_NET_SENDCHILD", "PERFDATA_CTX_PKT_NET_SENDPAR",
                                    "PERFDATA_CTX_PKT_INT_DATAPAR", "PERFDATA_CTX_PKT_INT_DATACHILD",
                                    "PERFDATA_CTX_PKT_FILTER", "PERFDATA_CTX_PKT_RECV_TO_FILTER",
                                    "PERFDATA_CTX_PKT_FILTER_TO_SEND", "PERFDATA_MAX_CTX"])
Network.add_method("enable_PerformanceData", retval("bool"),
                   [param("perfdata_metric_t", "metric"),
                    param("perfdata_context_t", "context")])
Network.add_method("disable_PerformanceData", retval("bool"),
                   [param("perfdata_metric_t", "metric"),
                    param("perfdata_context_t", "context")])
# TODO: collect_PerformanceData.
Network.add_method("print_PerformanceData", retval("void"),
                   [param("perfdata_metric_t", "metric"),
                    param("perfdata_context_t", "context")])
Network.add_method("clear_Events", retval("void"), [])
Network.add_method("num_EventsPending", retval("unsigned int"), [])
Network.add_method("next_Event", retval("MRN::Event*",
                                        caller_owns_return = False,
                                        reference_existing_object = True),
                   [])
Network.add_method("get_EventNotificationFd", retval("int"),
                   [param("int", "etype")])
Network.add_method("clear_EventNotificationFd", retval("void"),
                   [param("int", "etype")])
Network.add_method("close_EventNotificationFd", retval("void"),
                   [param("int", "etype")])
Network.add_method("register_EventCallback", retval("bool"),
                   [param("int", "iclass"),
                    param("int", "ityp"),
                    param("evt_cb_func", "ifunc"),
                    param("bool", "onetime", default_value = "false")])
Network.add_method("remove_EventCallbacks", retval("bool"),
                   [param("int", "iclass"),
                    param("int", "ityp")])
Network.add_method("set_FailureRecovery", retval("bool"),
                   [param("bool", "enable_recovery")])

# Generate the bindings. Redirect to a C++ file.
mod.generate(sys.stdout)
