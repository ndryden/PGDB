import os
if "4.4" not in os.path.realpath('/usr/bin/gcc'):
    if os.path.isfile('/usr/bin/gcc-4.4'):
        print "PGDB requires gcc 4.4. Will update gcc to symlink to gcc-4.4"
        os.unlink("/usr/bin/gcc")
        os.symlink('/usr/bin/gcc-4.4','/usr/bin/gcc')
    else:
        print "PGDB requires gcc 4.4 which is not installed"
if "4.4" not in os.path.realpath('/usr/bin/g++'):
    if os.path.isfile('/usr/bin/g++-4.4'):
        print "PGDB requires g++ 4.4. Will update g++ to symlink to g++-4.4"
        os.unlink("/usr/bin/g++")
        os.symlink('/usr/bin/g++-4.4','/usr/bin/g++')
    else:
        print "PGDB requires g++ 4.4 which is not installed"
