import sys, socket, mmap, struct, re, os.path
sys.path.append("/home/dryden2/lib64/python2.6/site-packages")
import posix_ipc

hostname = socket.gethostname()
gdb_semaphore = posix_ipc.Semaphore("/PGDBSemaphore" + hostname,
                                    posix_ipc.O_CREX)
gdb_shmem = posix_ipc.SharedMemory("/PGDBMem" + hostname,
                                   posix_ipc.O_CREX,
                                   size = 33554432)
gdb_mem = mmap.mmap(gdb_shmem.fd, gdb_shmem.size)
gdb_shmem.close_fd()
gdb_semaphore.release()

load_file_re = re.compile(r".*\.so.*")
load_file_bins = set(["mpitest", "test"])
manual = False

def clean_up():
    gdb_semaphore.unlink()
    gdb_semaphore.close()
    gdb_mem.close()
    gdb_shmem.unlink()

def load_file(filename):
    f = open(filename, "r")
    d = f.read()
    f.close()
    return d

def check_gdb_memory_flag():
    flag = struct.unpack_from("=B", gdb_mem, 1)[0]
    return flag == 1

def read_memory():
    struct.pack_into("=B", gdb_mem, 1, 0)
    size = struct.unpack_from("=I", gdb_mem, 2)[0]
    if size <= 0:
        print "Invalid size {0}".format(size)
        return False
    return struct.unpack_from("={0}s".format(size), gdb_mem, 6)[0]

def write_memory(data):
    struct.pack_into("=B", gdb_mem, 0, 1)
    size = len(data)
    return struct.pack_into("=I{0}s".format(size + 1), gdb_mem, 2, size, data)

def load_file_check(filename):
    filename = os.path.abspath(filename)
    base = os.path.basename(filename)
    if base in load_file_bins:
        return True
    if base[-4:] == ".gdb" or base[-3:] == ".py":
        return False
    if load_file_re.match(base) is not None:
        return True
    return False

def respond(prompt = False):
    gdb_semaphore.acquire()
    if check_gdb_memory_flag():
        filename = read_memory()
        check = load_file_check(filename)
        print "Check for {0}: {1}".format(filename, check)
        load = check
        if manual:
            load = True
            if prompt:
                y = raw_input("Load file {0}? ".format(filename))
                if y.lower() == "n":
                    load = False
        if load:
            try:
                data = load_file(filename)
                write_memory(data)
                print "Loaded {0} ({1}b)".format(filename, len(data))
            except IOError:
                write_memory("error")
                print "Could not find file, sent error"
        else:
            write_memory("error")
            print "Sent error"
    gdb_semaphore.release()
