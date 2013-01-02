"""A class for getting lines from source code for display.

This takes files and line numbers and returns the corresponding line from the source file. Files are
cached in memory to provide quick access and reduce system calls and disk load.

"""

class SourcePrinter:
    """Get lines from source code files."""

    def __init__(self):
        """Initialization."""
        self.filecache = {}

    def _load_and_cache_file(self, filename):
        """Load a file into the file cache."""
        with open(filename, "r") as f:
            self.filecache[filename] = f.readlines()

    def get_source_line(self, filename, line):
        """Get a given line from a source file.

        This caches the files contents in memory, under the assumption that source files should
        generally be small, and that there won't be too many read in.
        (If the former assumption is false, you are a bad programmer.)

        """
        try:
            if filename not in self.filecache:
                self._load_and_cache_file(filename)
        except IOError:
            return "Could not find " + filename

        lines = self.filecache[filename]
        line = int(line)
        line -= 1 # Account for being indexed by zero.
        if line >= len(lines):
            print "Bad line spec for {0}: got {1} have {2}".format(filename, line, len(lines))
            return None
        return lines[line].strip()
