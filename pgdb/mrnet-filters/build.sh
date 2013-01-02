#!/bin/sh

g++ -O0 -g -I/collab/usr/global/tools/mrnet/chaos_5_x86_64_ib/mrnet-4.0.0/include -L/collab/usr/global/tools/mrnet/chaos_5_x86_64_ib/mrnet-4.0.0/lib -lmrnet -lxplat -lpython2.6 -Wl,-rpath=/collab/usr/global/tools/mrnet/chaos_5_x86_64_ib/mrnet-4.0.0/lib -fPIC -shared -rdynamic -o test.so test.cc
