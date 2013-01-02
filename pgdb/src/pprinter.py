"""The main pretty-printer for printing nicely-formatted versions of the parsed MI output."""

from conf import gdbconf
from mi.gdbmi_parser import *
from mi.varobj import VariableObject, VariableObjectManager
from sourceprinter import SourcePrinter
import sys

class GDBMIPrettyPrinter:
    """This handles all pretty-printing.

    The process of pretty-printing involves using the GDBMIRecordIdentifier to determine
    information about the record, and then invoking a series of functions based on looking up
    relevant information in dictionaries and invoking functions stored there (think of them as
    jump-tables).

    If the GDB configuration specifies a dump_file, whenever pretty_print is called, the output
    from default_pretty_print is written to that file.

    The only functions that should be used, in general, are pretty_print and default_pretty_print.

    All pretty-printing functions except pretty_print return a string, and do not print on their own.
    If a function returns False to pretty_print, it will print the record using the default pretty
    printer.

    """

    def __init__(self, identifier):
        """Initialize the pretty printer.

        identifier is the GDBMIRecordIdentifier to use for record identification.

        This sets up a large number of dictionaries which are used by the functions to determine
        how they should proceed in printing.

        """
        self.identifier = identifier
        if gdbconf.print_dump_file:
            self.dump_file = open(gdbconf.print_dump_file, "wt")
        else:
            self.dump_file = None

        self.pprinters = {
            RESULT: self.result_pretty_print,
            ASYNC_EXEC: self.exec_pretty_print,
            ASYNC_NOTIFY: self.notify_pretty_print,
            STREAM_CONSOLE: self.console_pretty_print
            }
        self.result_pprinters = {
            "error": self.result_error_pretty_print,
            "done": self.result_done_pretty_print,
            "exit": self.result_exit_pretty_print
            }
        # These should return a tuple with the first element being an integer
        # indicating relative priority, and the second element being the data.
        # If present, the third element indicates other fields to be filtered.
        self.result_done_pprinters = {
            "breakpoint-created": self.result_done_breakpoint_created_pretty_print,
            "watchpoint-created": self.result_done_watchpoint_created_pretty_print,
            "access-watchpoint-created": self.result_done_access_watchpoint_created_pretty_print,
            "read-watchpoint-created": self.result_done_read_watchpoint_created_pretty_print,
            "stack": self.result_done_stack_pretty_print,
            "breakpoint-table": self.result_done_breakpoint_table_pretty_print,
            "var-created": self.result_done_var_created_pretty_print,
            "var-list-children": self.result_done_var_list_children_pretty_print,
            "var-info-type": self.result_done_var_info_type_pretty_print,
            "time": self.result_done_time_pretty_print,
            "thread-id": self.result_done_thread_id_pretty_print,
            "value": self.result_done_value_pretty_print,
            "feature-list": self.result_done_feature_list_pretty_print,
            "thread-groups-list": self.result_done_thread_groups_list_pretty_print,
            "threads-list": self.result_done_threads_list_pretty_print,
            "source-path": self.result_done_source_path_pretty_print,
            "path": self.result_done_path_pretty_print,
            "cwd": self.result_done_cwd_pretty_print,
            "frame": self.result_done_frame_pretty_print,
            "stack-depth": self.result_done_stack_depth_pretty_print,
            "stack-args": self.result_done_stack_args_pretty_print,
            "stack-variables": self.result_done_stack_variables_pretty_print,
            "asm-instructions": self.result_done_asm_instructions_pretty_print,
            "changed-registers": self.result_done_changed_registers_pretty_print,
            "register-names": self.result_done_register_names_pretty_print,
            "register-values": self.result_done_register_values_pretty_print
            }
        self.thread_group_pprinters = {
            "process": self.thread_group_process_pretty_print
            }
        self.exec_pprinters = {
            "stopped": self.exec_stopped_pretty_print,
            "running": self.exec_running_pretty_print
            }
        self.exec_stopped_pprinters = {
            "breakpoint-hit": self.exec_stopped_breakpoint_hit_pretty_print,
            "watchpoint-trigger": self.exec_stopped_watchpoint_trigger_pretty_print,
            "access-watchpoint-trigger": self.exec_stopped_access_watchpoint_trigger_pretty_print,
            "read-watchpoint-trigger": self.exec_stopped_read_watchpoint_trigger_pretty_print,
            "watchpoint-scope": self.exec_stopped_watchpoint_scope_pretty_print,
            "step-done": self.exec_stopped_step_done_pretty_print,
            "exit-signal": self.exec_stopped_exit_signal_pretty_print,
            "exited": self.exec_stopped_exited_pretty_print,
            "normal-exit": self.exec_stopped_normal_exit_pretty_print,
            "signal-received": self.exec_stopped_signal_received_pretty_print,
            "location-reached": self.exec_stopped_location_reached_pretty_print,
            "function-finished": self.exec_stopped_function_finished_pretty_print,
            "frame": self.exec_stopped_frame_pretty_print
            }
        self.signal_info_pprinters = {
            "EXC_BAD_ACCESS": self.signal_exc_bad_access_pretty_print
            }
        self.notify_pprinters = {
            "thread-group-added": self.notify_thread_group_added_pretty_print,
            "thread-group-started": self.notify_thread_group_started_pretty_print,
            "thread-group-exited": self.notify_thread_group_exited_pretty_print,
            "thread-created": self.notify_thread_created_pretty_print,
            "thread-exited": self.notify_thread_exited_pretty_print,
            "library-loaded": self.notify_library_loaded_pretty_print
            }
        self.varobj_display_pprinters = {
            "string": self.varobj_string_pretty_print,
            "array": self.varobj_array_pretty_print,
            "map": self.varobj_map_pretty_print
            }
        self.sourceprinter = SourcePrinter()

    def indent(self, level, s):
        """Return a given string with indentation prepended based upon the given level."""
        return ("   " * level) + s

    def default_pretty_print(self, record):
        """Do a simple pretty-print displaying the raw data within a record."""
        s = "[{0}] ({1}): ".format(record.token, record.record_type)
        if record.record_type == RESULT:
            return s + "result_class = {0}, results = {1}\n".format(record.result_class,
                                                                    record.results)
        elif record.record_type in [ASYNC_EXEC, ASYNC_STATUS, ASYNC_NOTIFY]:
            return s + "output_class = {0}, output = {1}\n".format(record.output_class,
                                                                 record.output)
        elif record.record_type in [STREAM_CONSOLE, STREAM_TARGET, STREAM_LOG]:
            return s + record.string + "\n"
        elif record.record_type == UNKNOWN:
            return s + "Unknown record: {0}\n".format(record.output)
        else:
            return s + "Unknown record type.\n"

    def pretty_print(self, record, tag = None, output = None):
        """Pretty-print a record.

        record is the record to pretty print.
        tag, if present, is prepended to each line of output.
        output is the stream to output to; defaults to stdout.

        """
        ident = self.identifier.identify(record)
        if tag is None:
            tag = ""
        raw = ""
        pretty = ""
        if self.dump_file:
            self.dump_file.write(self.default_pretty_print(record))
            self.dump_file.flush()
        if gdbconf.pretty_print == "no" or gdbconf.pretty_print == "both":
            raw = self.default_pretty_print(record)
        if gdbconf.pretty_print == "yes" or gdbconf.pretty_print == "both":
            if ident:
                if ident[0] in self.pprinters:
                    pretty = self.pprinters[record.record_type](record, ident)
            if not pretty:
                pretty = self.default_pretty_print(record)
        s = raw + pretty
        s = "\n".join(map(lambda x: "[{0}] {1}".format(tag, x), pretty.split("\n")[:-1])) + "\n"
        if not output:
            output = sys.stdout
        output.write(s)

    def frame_pretty_print(self, frame, print_source = False):
        """Pretty-print a stack frame."""
        if "level" in frame:
            line = "#{0}\t{1}".format(frame["level"], frame["addr"])
        else:
            line = frame["addr"]
        if "func" in frame:
            line += " in {0}".format(frame["func"])
            if "args" in frame:
                line += "("
                if len(frame["args"]):
                    for arg in frame["args"][:-1]:
                        line += "{0} = {1}, ".format(arg["name"], arg["value"])
                    line += "{0} = {1}".format(frame["args"][-1]["name"], frame["args"][-1]["value"])
                line += ")"
        if "file" in frame and "line" in frame:
            line += " at {0}:{1}".format(frame["file"], frame["line"])
            if print_source:
                line += "\n" + self.sourceprinter.get_source_line(frame["file"], frame["line"])
        return line

    def result_pretty_print(self, record, ident):
        """Pretty-print a result record."""
        if len(ident) > 1 and ident[1] in self.result_pprinters:
            return self.result_pprinters[ident[1]](record, ident)
        return False

    def result_error_pretty_print(self, record, ident):
        """Pretty-print an error result."""
        if "msg" in record.results:
            return "ERROR: {0}\n".format(record.results["msg"])
        return False

    def result_done_pretty_print(self, record, ident):
        """Pretty-print a done result, looking up the appropriate printer."""
        results = []
        if len(ident) == 2:
            return "Done.\n"
        for k in ident[2:]:
            if k in self.result_done_pprinters:
                results.append((k, self.result_done_pprinters[k](record, ident)))
        if not results:
            return "Done. {0}\n".format(record.results)
        # Remove anything with priority 0.
        results = filter(lambda x: x[1][0] != 0, results)
        results.sort(key = lambda x: x[1][0], reverse = True)
        # Construct the filter list.
        to_filter = []
        for i in results:
            if len(i[1]) == 3:
                to_filter += i[1][2]
        # Remove the filtered items. This is not so efficient, but should be fine for small things.
        for k in to_filter:
            results = filter(lambda x: x[0] != k, results)
        return " ".join(map(lambda x: x[1][1], results)) + "\n"

    def result_done_breakpoint_created_pretty_print(self, record, ident):
        """Pretty-print a breakpoint creation result."""
        bkpt = record.results["bkpt"]
        if "file" in bkpt:
            s = "Breakpoint {0} at {1}: {2}:{3} in {4}:\n{5}".format(
                bkpt["number"], bkpt["addr"], bkpt["file"], bkpt["line"], bkpt["func"],
                self.sourceprinter.get_source_line(bkpt["file"], bkpt["line"]))
        else:
            s = "Breakpoint {0} at {1}".format(bkpt["number"], bkpt["addr"])
        return (100, s)

    def result_done_watchpoint_created_pretty_print(self, record, ident):
        """Pretty-print a watchpoint creation result."""
        wpt = record.results["wpt"]
        return (100, "Watchpoint {0}: {1}".format(wpt["number"], wpt["exp"]))

    def result_done_access_watchpoint_created_pretty_print(self, record, ident):
        """Pretty-print an access watchpoint creation result."""
        wpt = record.results["hw-awpt"]
        return (100, "Access watchpoint {0}: {1}".format(wpt["number"], wpt["exp"]))

    def result_done_read_watchpoint_created_pretty_print(self, record, ident):
        """Pretty-print a read watchpoint creation result."""
        wpt = record.results["hw-rwpt"]
        return (100, "Read watchpoint {0}: {1}".format(wpt["number"], wpt["exp"]))

    def result_done_stack_pretty_print(self, record, ident):
        """Pretty-print the result of a backtrace (stack frames)."""
        s = ""
        for tup in record.results["stack"]:
            if tup[0] == "frame":
                s += self.frame_pretty_print(tup[1]) + "\n"
            else:
                s += str(tup) + "\n"
        return (100, s[:-1]) # Remove trailing newline.
    
    def result_done_breakpoint_table_pretty_print(self, record, ident):
        """Pretty-print a breakpoint table."""
        if len(record.results["BreakpointTable"]["body"]) == 0:
            s = "No breakpoints.\n"
        else:
            s = "Num\tType\t\tDisp\tEnb\tAddress\t\t\tWhat\n"
            for tup in record.results["BreakpointTable"]["body"]:
                if tup[0] == "bkpt":
                    bkpt = tup[1]
                    if "func" in bkpt:
                        at = "in {0} at {1}:{2}".format(bkpt["func"], bkpt["file"], bkpt["line"])
                    else:
                        at = "in {0}".format(bkpt["original-location"])
                    if "addr" in bkpt and bkpt["addr"]:
                        addr = bkpt["addr"]
                    else:
                        addr = "\t\t"
                    s += "{0}\t{1}\t{2}\t{3}\t{4}\t{5}\n".format(bkpt["number"],
                                                                   bkpt["type"],
                                                                   bkpt["disp"],
                                                                   bkpt["enabled"],
                                                                   addr,
                                                                   at)
                    if "cond" in bkpt:
                        s += "\tstop only if {0}\n".format(bkpt["cond"])
                    if "times" in bkpt and int(bkpt["times"]) > 0:
                        s += "\tbreakpoint hit {0} time(s)\n".format(bkpt["times"])
                    if "ignore" in bkpt:
                        s += "\tignore next {0} hits\n".format(bkpt["ignore"])
                else:
                    s += str(tup) + "\n"
        return (100, s[:-1]) # Remove tailing newline.

    def varobj_pretty_print(self, varobj, indent = 0, tag = None):
        """Pretty-print a variable object."""
        s = self.indent(indent, "")
        if varobj.display_hint in self.varobj_display_pprinters:
            s += self.varobj_display_pprinters[varobj.display_hint](varobj, indent) + "\n"
        else:
            if len(varobj.children):
                child_s = ""
                if varobj.get_name() in ["public", "protected", "private"]:
                    # Skip printing pseduo-children.
                    for child in varobj.children.values():
                        child_s += self.varobj_pretty_print(child, indent = indent)
                else:
                    if varobj.vartype:
                        child_s += "{0} {1} = {{\n".format(varobj.vartype, varobj.get_name())
                    else:
                        child_s += "{0} = {{\n".format(varobj.get_name())
                    for child in varobj.children.values():
                        child_s += self.varobj_pretty_print(child, indent = indent + 1)
                    child_s += self.indent(indent, "}\n")
                s += child_s.lstrip() # Prevent excessive indents.
            else:
                if varobj.vartype:
                    if varobj.value:
                        s += "{0} {1} = {2}\n".format(varobj.vartype, varobj.get_name(), varobj.value)
                    else:
                        s += "{0} {1}\n".format(varobj.vartype, varobj.get_name())
                else:
                    s += "{0}\n".format(varobj.get_name())
        if tag is not None:
            return "[{0}] ".format(tag) + s
        return s

    def varobj_string_pretty_print(self, varobj, indent = 0):
        """Pretty-print a varobj with a 'string' displayhint."""
        return "{0} = \"{1}\"".format(varobj.get_name(), varobj.value)

    def varobj_array_pretty_print(self, varobj, indent = 0):
        """Pretty-print a varobj with an 'array' displayhint."""
        if varobj.vartype[0:11] == "std::vector":
            print_type = "std::vector"
        elif varobj.vartype[0:10] == "std::deque":
            print_type = "std::deque"
        elif varobj.vartype[0:8] == "std::set":
            print_type = "std::set"
        elif varobj.vartype[0:13] == "std::multiset":
            print_type = "std::multiset"
        else:
            print_type = varobj.vartype
        if varobj.listed:
            if len(varobj.children) == 0:
                return "{0} {1} with 0 children: []".format(print_type, varobj.get_name())
            else:
                if varobj.more_children:
                    s = "{0} {1} with >{2} children: [\n".format(print_type, varobj.get_name(),
                                                                 len(varobj.children))
                else:
                    s = "{0} {1} with {2} children: [\n".format(print_type, varobj.get_name(),
                                                                len(varobj.children))
                for name, child in varobj.get_sorted_children():
                    s += self.varobj_pretty_print(child, indent = indent + 1)
                if varobj.more_children:
                    s += self.indent(indent, "(...)\n")
                return s + "]"
        else:
            return "{0} {1} with unknown children".format(print_type, varobj.get_name())

    def varobj_map_pretty_print(self, varobj, indent = 0):
        """Pretty-print a varobj with a 'map' displayhint."""
        # Note that mapes alternate between keys and values in their children.
        if varobj.vartype[0:8] == "std::map":
            print_type = "std::map"
        elif varobj.vartype[0:13] == "std::multimap":
            print_type = "std::multimap"
        elif varobj.vartype[0:18] in ["tr1::unordered_map", "std::unordered_map"]:
            print_type = "std::unordered_map"
        else:
            print_type = varobj.vartype
        if varobj.listed:
            if len(varobj.children) == 0:
                return "{0} {1} with 0 children: {{}}".format(print_type, varobj.get_name())
            else:
                if varobj.more_children:
                    s = "{0} {1} with >{2} children: {{\n".format(print_type, varobj.get_name,
                                                                  len(varobj.children))
                else:
                    s = "{0} {1} with {2} children: {{\n".format(print_type, varobj.get_name,
                                                             len(varobj.children))
                children = varobj.get_sorted_children()
                for i in range(0, len(varobj.children), 2):
                    s += "{0} = {1}".format(self.varobj_pretty_print(children[i][1],
                                                                     indent = indent + 1)[:-1],
                                            self.varobj_pretty_print(children[i + 1][1],
                                                                     indent = indent + 2))
                if varobj.more_children:
                    s += self.indent(indent, "(...)\n")
                return s + "}}"
        else:
            return "{0} {1} with unknown children".format(print_type, varobj.get_name())

    def result_done_var_created_pretty_print(self, record, ident):
        """Pretty-print the result of a variable object creation."""
        var = record.results
        varobj = VariableObjectManager.create_var_obj(var)
        return (100, self.varobj_pretty_print(varobj)[:-1], ["value"])

    def result_done_var_list_children_pretty_print(self, record, ident):
        """Pretty-print the result of listing a variable object's children."""
        s = ""
        for child_tup in record.results["children"]:
            if child_tup[0] != "child":
                print "Unknown entry in var list children!"
                return False
            child = child_tup[1]
            if "type" in child:
                vartype = child["type"]
                if "value" in child:
                    value = child["value"]
                else:
                    value = None
            else:
                vartype = None
                value = None
            if "displayhint" in child:
                displayhint = child["displayhint"]
            else:
                displayhint = None
            if "dynamic" in child:
                dynamic = child["dynamic"]
            else:
                dynamic = False
            varobj = VariableObject(child["name"], vartype, value = value,
                                    thread_id = child["thread-id"],
                                    display_hint = displayhint,
                                    is_dynamic = dynamic, num_child = child["numchild"])
            s += self.varobj_pretty_print(varobj)
        return (100, s[:-1]) # Remove trailing newline.

    def result_done_var_info_type_pretty_print(self, record, ident):
        """Pretty-print the result of querying a variable object's type."""
        return (100, record.results["type"])

    def result_done_time_pretty_print(self, record, ident):
        """Pretty-print timing information; presently deletes the information."""
        return (0, "")

    def result_done_thread_id_pretty_print(self, record, ident):
        """Pretty-print a thread ID."""
        return (5, "(Thread ID {0})".format(record.results["thread-id"]))

    def result_done_value_pretty_print(self, record, ident):
        """Pretty-print a value that a result returns."""
        return (10, str(record.results["value"]))

    def result_done_feature_list_pretty_print(self, record, ident):
        """Pretty-print a feature list."""
        s = ""
        for feature in record.results["features"]:
            s += feature + "\n"
        return (100, s[:-1])

    def result_done_thread_groups_list_pretty_print(self, record, ident):
        """Pretty-print a thread groups listing."""
        groups = record.results["groups"]
        s = ""
        if len(groups) == 0:
            s = "No groups.\n"
        else:
            for group in groups:
                if group["type"] in self.thread_group_pprinters:
                    s += self.thread_group_pprinters[group["type"]](group)
                else:
                    s += "Unknown thread group type: {0}\n".format(group)
        return (100, s[:-1])

    def thread_group_process_pretty_print(self, group):
        """Pretty print a thread group."""
        s = ""
        if "description" in group:
            # This probably came from a thread groups list --available.
            s = "{0} {1}:{2}".format(group["id"], group["user"], group["description"])
            if "threads" in group:
                s += ", threads:\n" + self.threads_list_pretty_print(group["threads"])
            else:
                s += "\n"
        else:
            # A "regular" group listing.
            s = "{0}".format(group["id"])
            if "pid" in group and "executable" in group:
                s += ", PID {0}, {1}".format(group["pid"], group["executable"])
            if "num_children" in group:
                s += ", {0} children".format(group["num_children"])
            if "threads" in group:
                s += ", threads:\n" + self.threads_list_pretty_print(group["threads"])
            elif "cores" in group:
                s += ", on core(s) {0}\n".format(",".join(group["cores"]))
        return s

    def threads_list_pretty_print(self, threads):
        """Pretty-print a threads listing, without a record."""
        if len(threads) == 0:
            return "No threads.\n"
        s = "ID\tTarget ID\t\t\t\t\tCore\tFrame\n"
        for thread in threads:
            if "target-id" in thread:
                # 41 = len("Target ID") + (4 * 8) -- A tab is length 8.
                target_id = thread["target-id"].ljust(41)
            else:
                target_id = " " * 41
            if "core" in thread:
                core = thread["core"]
            else:
                core = "\t"
            if "frame" in thread:
                frame = self.frame_pretty_print(thread["frame"])
            else:
                frame = ""
            s += "{0}\t{1}\t{2}\t{3}\n".format(thread["id"], target_id, core, frame)
        return s

    def result_done_threads_list_pretty_print(self, record, ident):
        """Pretty-print a threads listing."""
        s = self.threads_list_pretty_print(record.results["threads"])
        return (100, s[:-1])

    def result_done_source_path_pretty_print(self, record, ident):
        """Pretty-print the current source path."""
        return (100, record.results["source-path"])

    def result_done_path_pretty_print(self, record, ident):
        """Pretty-print the current path."""
        return (100, record.results["path"])

    def result_done_cwd_pretty_print(self, record, ident):
        """Pretty-print the current working directory."""
        return (100, record.results["cwd"])

    def result_done_frame_pretty_print(self, record, ident):
        """Pretty-print a frame."""
        return (100, self.frame_pretty_print(record.results["frame"], print_source = True))

    def result_done_stack_depth_pretty_print(self, record, ident):
        """Pretty-print the stack depth."""
        return (100, record.results["depth"])

    def result_done_stack_args_pretty_print(self, record, ident):
        """Pretty-print a list of arguments on the stack."""
        s = ""
        for tup in record.results["stack-args"]:
            frame = tup[1]
            s += "#{0}".format(frame["level"])
            for arg in frame["args"]:
                if isinstance(arg, tuple):
                    s += " {0},".format(arg[1])
                elif "value" in arg:
                    s += " {0} = {1},".format(arg["name"], arg["value"])
            s = s[:-1] + "\n"
        return (100, s[:-1])

    def result_done_stack_variables_pretty_print(self, record, ident):
        """Pretty-print a list of variables in the frame."""
        s = ""
        for var in record.results["variables"]:
            if "value" in var:
                s += "{0} = {1}\n".format(var["name"], var["value"])
            else:
                s += "{0}\n".format(var["name"])
        return (100, s[:-1])

    def result_done_asm_instructions_pretty_print(self, record, ident):
        """Pretty-print assembly instructions from a disassembly."""
        s = ""
        instrs = record.results["asm_insns"]
        if len(instrs) == 0:
            return (100, "")
        # Check if this is mixed source and assembly.
        if isinstance(instrs[0], tuple) and instrs[0][0] == "src_and_asm_line":
            cur_func = ""
            for tup in instrs:
                line = tup[1]
                s += "{0}: {1}\n".format(line["line"], self.sourceprinter.get_source_line(line["file"],
                                                                                          line["line"]))
                for inst in line["line_asm_insn"]:
                    if inst["func-name"] != cur_func:
                        cur_func = inst["func-name"]
                        s += "Function {0}\n".format(cur_func)
                    s += self.indent(1, "{0} <+{1}>:\t{2}\n".format(inst["address"], inst["offset"],
                                                                    inst["inst"]))
        else:
            cur_func = ""
            for inst in instrs:
                if inst["func-name"] != cur_func:
                    cur_func = inst["func-name"]
                    s += "Function {0}\n".format(cur_func)
                s += self.indent(1, "{0} <+{1}>:\t{2}\n".format(inst["address"], inst["offset"],
                                                                inst["inst"]))
        return (100, s[:-1])

    def result_done_changed_registers_pretty_print(self, record, ident):
        """Pretty-print the list of changed registers."""
        return (100, ", ".join(record.results["changed-registers"]))

    def result_done_register_names_pretty_print(self, record, ident):
        """Pretty-print the list of register names."""
        s = ""
        for i, reg in enumerate(record.results["register-names"]):
            if reg != "":
                s += "{0}: {1}\n".format(i, reg)
        return (100, s[:-1])

    def result_done_register_values_pretty_print(self, record, ident):
        """Pretty-print the values in registers."""
        s = ""
        for val in record.results["register-values"]:
            s += "{0} = {1}\n".format(val["number"], val["value"])
        return (100, s[:-1])

    def result_exit_pretty_print(self, record, ident):
        """Pretty-print an exit result."""
        return "Exit.\n"

    def exec_pretty_print(self, record, ident):
        """Pretty-print an exec async record."""
        if len(ident) > 1 and ident[1] in self.exec_pprinters:
            return self.exec_pprinters[ident[1]](record, ident)
        return False

    def exec_stopped_pretty_print(self, record, ident):
        """Pretty-print an exec stopped record."""
        if len(ident) > 2 and ident[2] in self.exec_stopped_pprinters:
            return self.exec_stopped_pprinters[ident[2]](record, ident)
        return False

    def exec_stopped_breakpoint_hit_pretty_print(self, record, ident):
        """Pretty-print a breakpoint hit stop."""
        return "Breakpoint {0}:\n{1}\n".format(record.output["bkptno"],
                                               self.frame_pretty_print(record.output["frame"],
                                                                       print_source = True))

    def exec_stopped_watchpoint_trigger_pretty_print(self, record, ident):
        """Pretty-print a watchpoint trigger stop."""
        wpt = record.output["wpt"]
        val = record.output["value"]
        return "Watchpoint {0}: {1}\nOld value = {2}\nNew value = {3}\n{4}\n".format(
            wpt["number"], wpt["exp"], val["old"], val["new"],
            self.frame_pretty_print(record.output["frame"], print_source = True))

    def exec_stopped_access_watchpoint_trigger_pretty_print(self, record, ident):
        """Pretty-print an access watchpoint trigger stop."""
        wpt = record.output["hw-awpt"]
        val = record.output["value"]
        return "Access watchpoint {0}: {1}\nValue = {2}\n{3}\n".format(
            wpt["number"], wpt["exp"], val["new"], self.frame_pretty_print(record.output["frame"],
                                                                           print_source = True))

    def exec_stopped_read_watchpoint_trigger_pretty_print(self, record, ident):
        """Pretty-print a read watchpoint trigger stop."""
        wpt = record.output["hw-rwpt"]
        val = record.output["value"]
        return "Read watchpoint {0}: {1}\nValue = {2}\n{3}\n".format(
            wpt["number"], wpt["exp"], val["value"], self.frame_pretty_print(record.output["frame"],
                                                                             print_source = True))

    def exec_stopped_watchpoint_scope_pretty_print(self, record, ident):
        """Pretty-print a stop due to a watchpoint leaving the current scope."""
        return "Watchpoint {0} deleted because it is not in scope.\n{1}\n".format(
            record.output["wpnum"], self.frame_pretty_print(record.output["frame"],
                                                            print_source = True))

    def exec_stopped_step_done_pretty_print(self, record, ident):
        """Pretty-print a stop due to stepping finishing."""
        return "{0}\n".format(self.frame_pretty_print(record.output["frame"],
                                                      print_source = True))

    def exec_stopped_exit_signal_pretty_print(self, record, ident):
        """Pretty-print a stop due to exiting on a signal."""
        name = record.output["signal-name"]
        s = "Received signal {0}, {1}".format(name, record.output["signal-meaning"])
        if name in self.signal_info_pprinters:
            s += " " + self.signal_info_pprinters[name](record, ident)
        else:
            s += "."
        return s + "\n"

    def signal_exc_bad_access_pretty_print(self, record, ident):
        """Pretty-print information on receiving an EXC_BAD_ACCESS signal."""
        return "{0} at {1}".format(record.output["access-reason"], record.output["address"])

    def exec_stopped_exited_pretty_print(self, record, ident):
        """Pretty-print a stop due to exiting with an error code."""
        return "Exited with code {0}.\n".format(record.output["exit-code"])

    def exec_stopped_normal_exit_pretty_print(self, record, ident):
        """Pretty-print a stop due to a normal exit."""
        return "Program exited normally.\n"

    def exec_stopped_signal_received_pretty_print(self, record, ident):
        """Pretty-print a stop due to receiving a signal."""
        return "Received signal {0}, {1}\n".format(record.output["signal-name"],
                                                 record.output["signal-meaning"])

    def exec_stopped_location_reached_pretty_print(self, record, ident):
        """Pretty-print a stop due to reaching a desired location."""
        return "Location reached.\n{0}\n".format(self.frame_pretty_print(record.output["frame"],
                                                                         print_source = True))

    def exec_stopped_function_finished_pretty_print(self, record, ident):
        """Pretty-print a stop due to a function finishing."""
        if "return-value" in record.output:
            return "Function finished, return = {0}\n{1}\n".format(
                record.output["return-value"], self.frame_pretty_print(record.output["frame"],
                                                                       print_source = True))
        else:
            return "Function finished, returned void.\n{0}\n".format(
                self.frame_pretty_print(record.output["frame"], print_source = True))

    def exec_stopped_frame_pretty_print(self, record, ident):
        """Pretty-print a stop that includes frame information."""
        return "Stopped.\n" + self.frame_pretty_print(record.output["frame"],
                                                      print_source = True) + "\n"

    def exec_running_pretty_print(self, record, ident):
        """Pretty-print that a thread is running."""
        return "Thread ID {0} running.\n".format(record.output["thread-id"])

    def notify_pretty_print(self, record, ident):
        """Pretty-print a notify async record."""
        if len(ident) > 1 and ident[1] in self.notify_pprinters:
            return self.notify_pprinters[ident[1]](record, ident)
        return False

    def notify_thread_group_added_pretty_print(self, record, ident):
        """Pretty-print a notification that a thread group was added."""
        return "Thread group {0} added.\n".format(record.output["id"])
    
    def notify_thread_group_started_pretty_print(self, record, ident):
        """Pretty-print a notification that a thread group was started."""
        return "Thread group {0} started, PID = {1}.\n".format(record.output["id"],
                                                             record.output["pid"])

    def notify_thread_group_exited_pretty_print(self, record, ident):
        """Pretty-print a notification that a thread group has exited."""
        return "Thread group {0} exited.\n".format(record.output["id"])

    def notify_thread_created_pretty_print(self, record, ident):
        """Pretty-print a notification that a thread was created."""
        return "Thread {0} (group {1}) created.\n".format(record.output["id"],
                                                        record.output["group-id"])

    def notify_thread_exited_pretty_print(self, record, ident):
        """Pretty-print a notification that a thread has exited."""
        return "Thread {0} (group {1}) exited.\n".format(record.output["id"],
                                                       record.output["group-id"])

    def notify_library_loaded_pretty_print(self, record, ident):
        """Pretty-print a notification that a library was loaded."""
        return "{0} loaded ({1} symbol(s)).\n".format(record.output["target-name"],
                                                    record.output["symbols-loaded"])

    def console_pretty_print(self, record, ident):
        """Pretty-print a console stream record."""
        s = record.string
        # Strip quotes.
        if s[0] == '"' and s[-1] == '"':
            s = s[1:-1]
        # Convert literal "\n"s to real newlines.
        s = s.replace("\\n", "\n")
        if s == "\n":
            # If we have just a newline, just return that.
            return s
        return s + "\n"
