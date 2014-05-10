# Path to LaunchMON.
lmon_path = ""
# Path to RSH.
lmon_rsh_path = ""

# The library for the LaunchMON front-end.
lmon_fe_lib = lmon_path + "/lib/libmonfeapi.so"
# The library for the LaunchMON back-end.
lmon_be_lib = lmon_path + "/lib/libmonbeapi.so"
# The version of the LaunchMON API.
lmon_version = 900100
# LaunchMON environment variables.
lmon_environ = {"LMON_REMOTE_LOGIN": lmon_rsh_path,
                "LMON_PREFIX": lmon_path,
                "LMON_LAUNCHMON_ENGINE_PATH": lmon_path + "/bin/launchmon"}
