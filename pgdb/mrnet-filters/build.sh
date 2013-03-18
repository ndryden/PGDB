#!/bin/sh

g++ -Wall -Wextra -O0 -g -I/home/ndryden/include -L/home/ndryden/lib -Wl,-rpath=/home/ndryden/lib -fPIC -shared -rdynamic -o test.so test.cc -lmrnet -lxplat -lpython2.7
