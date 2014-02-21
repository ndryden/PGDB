import os
print "Yama kernel patches must be disabled for PGDB to work. This is a potential security risk."
a = raw_input('Continue? y or n: ')
if a=='y':
    os.system("echo \"0\" | sudo tee /proc/sys/kernel/yama/ptrace_scope")
else:
    print "exiting..."
