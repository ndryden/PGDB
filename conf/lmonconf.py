# Whether to use LaunchMON 1.0 or not.
use_lmon_10 = True
if use_lmon_10:
    # The library for the LaunchMON front-end.
    lmon_fe_lib = "/collab/usr/global/tools/launchmon/chaos_5_x86_64_ib/launchmon-1.0.0-20120608/lib/libmonfeapi.so"
    # The library for the LaunchMON back-end.
    lmon_be_lib = "/collab/usr/global/tools/launchmon/chaos_5_x86_64_ib/launchmon-1.0.0-20120608/lib/libmonbeapi.so"
    # The version of the LaunchMON API.
    lmon_version = 900100
    # LaunchMON environment variables.
    lmon_environ = {"LMON_REMOTE_LOGIN": "/usr/bin/rsh",
                    "LMON_PREFIX": "/collab/usr/global/tools/launchmon/chaos_5_x86_64_ib/launchmon-1.0.0-20120608",
                    "LMON_LAUNCHMON_ENGINE_PATH": "/collab/usr/global/tools/launchmon/chaos_5_x86_64_ib/launchmon-1.0.0-20120608/bin/launchmon"}
else:
    # The library for the LaunchMON front-end.
    lmon_fe_lib = "/usr/local/tools/launchmon/lib/lmonfeapi.so"
    # The library for the LaunchMON back-end.
    lmon_be_lib = "/usr/local/tools/launchmon/lib/lmonbeapi.so"
    # The version of the LaunchMON API.
    lmon_version = 900072
    # LaunchMON environment variables.
    lmon_environ = {"LMON_REMOTE_LOGIN": "/usr/bin/rsh",
                    "LMON_PREFIX": "/usr/local/tools/launchmon",
                    "LMON_LAUNCHMON_ENGINE_PATH": "/usr/local/tools/launchmon/bin/launchmon"}
