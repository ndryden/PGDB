#include <stdio.h>
#include <sys/types.h>
#include <unistd.h>
//#include <python2.6/Python.h>

#include "mrnet/MRNet.h"

extern "C" {

  using namespace MRN;

  const char* test_format_string = "%s";

  /*  __attribute__ ((constructor)) void init() {
    pid_t pid = getpid();
    printf("Init on %d\n", pid);
    //Py_Initialize();
  }

  __attribute__ ((destructor)) void fini() {
    pid_t pid = getpid();
    printf("Fini on %d\n", pid);
    //Py_Finalize();
    }*/

  void test(std::vector<PacketPtr> &packets_in, std::vector<PacketPtr> &packets_out,
	    std::vector<PacketPtr> &packets_out_reverse, void** state, PacketPtr& config_params,
	    const TopologyLocalInfo& topo_info) {
    //PyRun_SimpleString("print \"Hello, world!\"\n");
    size_t i;
    for (i = 0; i < packets_in.size(); ++i) {
      packets_out.push_back(packets_in[i]);
    }
  }

} /* extern "C" */
