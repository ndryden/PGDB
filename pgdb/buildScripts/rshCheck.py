import os
a = os.path.realpath("/usr/bin/rsh")
if "ssh" in a:
    os.unlink("usr/bin/rsh")
    os.symlink("/etc/alternatives/rsh", "usr/bin/rsh")
