import os
a = os.path.realpath("/usr/bin/rsh")
if "ssh" in a:
    os.system("rm /usr/bin/rsh"
    os.system("ln -s /etc/alternatives/rsh /usr/bin/rsh")
