"""Pretty-printer for nicely-formatted versions of parsed MI output."""

from conf import gdbconf
import sys

class GDBMIPrettyPrinter:
    """This handles all pretty-printing.

    If the GDB configuration specifies a dump_file, whenever pretty_print is
    called, the output from default_pretty_print is written to that file.

    To be pretty-printed, an object should implement the pretty_print function.
    This function should return either a list of strings, which will be printed
    using the convention that each string in the list is one line; or it should
    return None, in which case the object will be converted to a string directly
    and the result printed.

    If an object does not implement pretty_print, it is converted to a string.

    """

    def __init__(self):
        """Initialize the pretty printer."""
        if gdbconf.print_dump_file:
            self.dump_file = open(gdbconf.print_dump_file, "wt")
        else:
            self.dump_file = None

    @staticmethod
    def indent(level, string):
        """Prepend level indents to string."""
        return ("   " * level) + string

    @staticmethod
    def default_pretty_print(record):
        """Do a simple pretty-print displaying the raw data within a record."""
        return str(record)

    def pretty_print(self, record, tag=None, output=None):
        """Pretty-print a record.

        record is the record to pretty print.
        tag, if present, is prepended to each line of output.
        output is the stream to output to; defaults to stdout.

        """
        raw = ""
        pretty = ""
        if self.dump_file:
            self.dump_file.write(self.default_pretty_print(record))
            self.dump_file.flush()
        if gdbconf.pretty_print == "no" or gdbconf.pretty_print == "both":
            raw = "[{0}] {1}".format(tag, self.default_pretty_print(record))
            if raw[-1] != "\n":
                raw += "\n"
        if gdbconf.pretty_print == "yes" or gdbconf.pretty_print == "both":
            try:
                line = record.pretty_print()
                if line is None:
                    pretty = "[{0}] {1}".format(tag,
                                                self.default_pretty_print(
                                                    record))
                    if pretty[-1] != "\n":
                        pretty += "\n"
                else:
                    pretty = "\n".join(["[{0}] {1}".format(tag, x)
                                        for x in line]) + "\n"
            except AttributeError:
                pretty = self.default_pretty_print(record)
        string = raw + pretty
        output = output or sys.stdout
        output.write(string)
