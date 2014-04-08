import os
MRNetDir = "/home/ndryden"
buildCommand = "g++ -Wall -Wextra -O0 -g -I"+MRNetDir+"/include -L"+MRNetDir+"/lib -Wl,-rpath="+MRNetDir+"/lib -fPIC -shared -rdynamic -o arec_filter.so arec_filter.cc -lmrnet -lxplat -lpython2.7 -lboost_timer-mt -lboost_system-mt"
print buildCommand
os.system(buildCommand);