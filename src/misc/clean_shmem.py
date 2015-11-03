import sys, socket
sys.path.append("/home/dryden2/lib64/python2.6/site-packages")
import posix_ipc

hostname = socket.gethostname()
try:
    gdb_semaphore = posix_ipc.Semaphore("/PGDBSemaphore" + hostname)
    gdb_semaphore.unlink()
    gdb_semaphore.close()
    print "Closed semaphore."
except posix_ipc.ExistentialError:
    pass
try:
    gdb_shmem = posix_ipc.SharedMemory("/PGDBMem" + hostname)
    gdb_shmem.unlink()
    print "Closed shared memory."
except posix_ipc.ExistentialError:
    pass
