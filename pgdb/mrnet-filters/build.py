#!/usr/bin/env python
"""Quick Python script to build the arec filter."""

import os
mrnet_path = "/home/ndryden/mrnet"
# Version of python.
python_lib = "python2.7"
# Boost libraries that need to be used when building.
boost_libs = ["boost_timer-mt", "boost_system-mt"]
build_command = "g++ -Wall -Wextra -O0 -g -I" + mrnet_path + "/include -L" + mrnet_path + "/lib -Wl,-rpath=" + mrnet_path + "/lib -fPIC -shared -rdynamic -o arec_filter.so arec_filter.cc -lmrnet -lxplat" -lpython2.7 -lboost_timer-mt -lboost_system-mt
build_command += " -l" + python_lib
build_command += "".join([" -l" + lib for lib in boost_libs])
print build_command
os.system(build_command);
