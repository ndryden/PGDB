#Path to LaunchMON
lmonPath = ""
#Path to RSH
lmonRSHPath = ""





# The library for the LaunchMON front-end.
lmon_fe_lib = lmonPath+"/lib/libmonfeapi.so"
# The library for the LaunchMON back-end.
lmon_be_lib = lmonPath+"/lib/libmonbeapi.so"
# The version of the LaunchMON API.
lmon_version = 900100
# LaunchMON environment variables.
lmon_environ = {"LMON_REMOTE_LOGIN": lmonRSHPath,
                "LMON_PREFIX": lmonPath,
                "LMON_LAUNCHMON_ENGINE_PATH": lmonPath+"/bin/launchmon"}
