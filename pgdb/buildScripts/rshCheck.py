import os
a = os.path.realpath("/usr/bin/rsh")
if "ssh" in a:
    os.system("ln -s /usr/bin/rsh /etc/alternatives/rsh")
