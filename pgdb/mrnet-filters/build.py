#!/usr/bin/env python
"""Quick Python script to build the arec filter."""

import os
mrnet_path = "/home/ndryden/mrnet"
build_command = "g++ -Wall -Wextra -O0 -g -I" + mrnet_dir + "/include -L" + mrnet_dir + "/lib -Wl,-rpath=" + mrnet_dir + "/lib -fPIC -shared -rdynamic -o arec_filter.so arec_filter.cc -lmrnet -lxplat -lpython2.7 -lboost_timer-mt -lboost_system-mt"
print build_command
os.system(build_command);
