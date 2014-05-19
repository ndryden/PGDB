"""PGDB scalable binary distribution (SBD) system.

This handles deploying files via MRNet instead of the parallel filesystem.

"""

import os.path
from gdb_shared import GDBMessage, FILE_DATA

class SBDFE:
    """Front-end SBD system."""

    def __init__(self, comm):
        """Initialization.

        comm is the FE comm object.

        """
        self.comm = comm
        self.loaded_files = set()

    def load_file(self, filename):
        """Load a file and broadcast it.

        This will attempt to load a file, and broadcasts either the file or an
        error notice. If the file has already been loaded, this does nothing.

        """
        if filename in self.loaded_files:
            # File has been broadcast to everyone.
            # TODO: Time this out somehow so that further requests can be made.
            return
        if not os.path.isfile(filename):
            print "Invalid SBD load file request for '{0}'".format(filename)
            self.comm.send(GDBMessage(FILE_DATA, filename = filename,
                                      data = None, error = True),
                           self.comm.broadcast)
            return
        try:
            f = open(filename, "rb")
        except IOError as e:
            print "Cannot open {0} for SBD load file: {1}.".format(filename,
                                                                   e.strerror)
            self.comm.send(GDBMessage(FILE_DATA, filename = filename,
                                      data = None, error = True),
                           self.comm.broadcast)
            return
        try:
            data = f.read()
        except IOError as e:
            print "Cannot read {0} for SBD load file: {1}.".format(filename,
                                                                   e.strerror)
            self.comm.send(GDBMessage(FILE_DATA, filename = filename,
                                      data = None, error = True),
                           self.comm.broadcast)
            return
        f.close()
        self.loaded_files.add(filename)
        self.comm.send(GDBMessage(FILE_DATA, filename = filename,
                                  data = data, error = False),
                       self.comm.broadcast)

class SBDBE:
    """Back-end SBD system."""

    def __init__(self):
        pass
