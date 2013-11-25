#!/bin/sh

g++ -Wall -Wextra -O0 -g -I/home/ndryden/include -L/home/ndryden/lib -Wl,-rpath=/home/ndryden/lib -fPIC -shared -rdynamic -o arec_filter.so arec_filter.cc -lmrnet -lxplat -lpython2.7 -lboost_timer-mt -lboost_system-mt
