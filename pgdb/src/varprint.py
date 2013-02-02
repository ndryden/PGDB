"""Class for managing variable printing.

This is intended for the back-end GDB processes, to manage variable printing
and the like.

"""

from conf import gdbconf
from mi.commands import Command
from mi.varobj import VariableObjectManager
from gdb_shared import *

class VariablePrinter:
    """Manage variable printing on the back-end."""

    def __init__(self, be):
        """Initialization.

        be is the GDBBE associated with this.

        """
        self.be = be
        self.comm = be.comm
        self.varobjs = be.varobjs
        self.run_gdb_command = be.run_gdb_command
        self.varprint_id = 0
        self.varprint_stacks = {}

    def varprint_handler(self, msg):
        """Handle the varprint message and begin the varprint sequence.

        The message has the fields
        ranks - the ranks to query.
        name - the name of the variable.

        To varprint, we first run varprint_update, to update our cached varobjs.
        Then we run another handler that checks if we have the variable object already.
        If not, we do a depth-first search and eventually return the result.

        """
        for rank in msg.ranks.intersect(self.comm.get_mpiranks()):
            self.varprint_update(msg.name, rank)

    def varprint_handler2(self, name, rank):
        """Follow-up varprint handler after udating, starts the DFS."""
        # Check if we already have the variable object.
        varobj = self.varobjs[rank].get_var_obj(name)
        if varobj:
            if not varobj.listed or varobj.more_children:
                # If we explicitly list this variable, print all of its children.
                self.varprint_start_no_create(rank, varobj, name,
                                              max_children = sys.maxsize, reset_maxes = True)
            else:
                self.comm.send(GDBMessage(VARPRINT_RES_MSG, varobj = varobj, rank = rank, err = False), self.comm.frontend)
        else:
            # We do not. Start from the closest ancestor we have.
            ancestor = self.varobjs[rank].get_lowest_ancestor(name)
            if ancestor:
                # Start by listing the children of the ancestor.
                self.varprint_start_no_create(rank, ancestor, name)
            else:
                self.varprint_start(rank, name)

    def varprint_update(self, name, rank):
        """Check for updates on any of our variable objects."""
        def _update_handler(record):
            if "changelist" not in record.results:
                print "Got a bad update record."
                return True
            for change in record.results["changelist"]:
                varobj = self.varobjs[rank].get_var_obj(change["name"])
                if varobj:
                    # Potentially, a variable object could be manually created that we're not tracking.
                    if "in_scope" in change:
                        if change["in_scope"] in ["false", "invalid"]:
                            self.varobjs[rank].del_var_obj(varobj)
                            del varobj # This probably isn't necessary.
                            return False
                    if "type_changed" in change and change["type_changed"] == "true":
                        self.varobjs[rank].del_var_obj(varobj)
                        del varobj
                        return False
                    if "value" in change:
                        varobj.value = change["value"]
                    if "dynamic" in change:
                        varobj.is_dynamic = change["dynamic"]
                    if "displayhint" in change:
                        varobj.display_hint = change["displayhint"]
                    if "num_new_children" in change:
                        new_num = int(change["new_num_children"])
                        if new_num < len(varobj.children):
                            # There has been a removal, so we no longer have child information.
                            varobj.children = []
                            varobj.listed = False
                            varobj.has_more = False
                        else:
                            if "new_children" in change:
                                for child in change["new_children"]:
                                    varobj = VariableObjectManager.create_var_obj(child)
                                    if not varobj:
                                        print "Could not create child varobj!"
                                        return True
                                    if not self.varobjs[rank].add_var_obj(varobj):
                                        print "Could not add child varobj!"
                                        return True
            self.varprint_handler2(name, rank)
        tokens = self.run_gdb_command(Command("var-update", args = ("1", "*")), rank)
        self.be.add_token_handler(tokens[rank], _update_handler)

    def varprint_start(self, rank, name, max_depth = gdbconf.varprint_max_depth,
                       max_children = gdbconf.varprint_max_children, reset_maxes = False):
        """Start a varprint command sequence by creating the varobj in GDB."""
        v_id = self.varprint_id
        self.varprint_id += 1
        base_name = VariableObjectManager.get_base_name(name)
        branch_depth = max_depth + VariableObjectManager.get_name_depth(name)
        def _list_handler(record):
            return self.varprint_dfs(record, rank, v_id, name, max_depth = max_depth,
                                     max_children = max_children, reset_maxes = False,
                                     branch_depth = branch_depth, branch_name = name)
        def _create_handler(record):
            varobj = VariableObjectManager.create_var_obj(record.results)
            if not varobj:
                # Bad variable name.
                return True
            if not self.varobjs[rank].add_var_obj(varobj):
                print "Could not add varobj."
            if int(varobj.num_child) > 0 or varobj.is_dynamic:
                # Set up our stack.
                self.varprint_stacks[v_id] = [(varobj, 0)]
                tokens = self.run_gdb_command(Command("var-list-children", args = ("1", record.results["name"])),
                                              rank)
                self.be.add_token_handler(tokens[rank], _list_handler)
            else:
                self.comm.send(GDBMessage(VARPRINT_RES_MSG, varobj = varobj, rank = rank, err = False), self.comm.frontend)
        tokens = self.run_gdb_command(Command("var-create", args = (base_name, "*", base_name)), rank)
        self.be.add_token_handler(tokens[rank], _create_handler)

    def varprint_start_no_create(self, rank, varobj, name, max_depth = gdbconf.varprint_max_depth,
                                 max_children = gdbconf.varprint_max_children, reset_maxes = False):
        """Start a varprint sequence where we have already created the variable object."""
        v_id = self.varprint_id
        self.varprint_id += 1
        self.varprint_stacks[v_id] = [(varobj, 0)]
        branch_depth = max_depth = VariableObjectManager.get_name_depth(name)
        def _list_handler(record):
            return self.varprint_dfs(record, rank, v_id, name, max_depth = max_depth,
                                     max_children = max_children, reset_maxes = reset_maxes,
                                     branch_depth = branch_depth, branch_name = name)
        tokens = self.run_gdb_command(Command("var-list-children", args = ("1", '"' + varobj.name + '"')), rank)
        self.be.add_token_handler(tokens[rank], _list_handler)

    def varprint_dfs(self, record, rank, v_id, name, max_depth = gdbconf.varprint_max_depth,
                     max_children = gdbconf.varprint_max_children,
                     reset_maxes = False, branch_depth = None, branch_name = None):
        """Do the depth-first search for expanding a variable object's children."""
        cur_varobj, parent_depth = self.varprint_stacks[v_id].pop()
        cur_varobj.listed = True
        if "has_more" not in record.results:
            self.comm.send(GDBMessage(VARPRINT_RES_MSG, rank = rank, err = True, msg = "Got bad variable data."), self.comm.frontend)
        elif "children" in record.results:
            if len(record.results["children"]) > max_children:
                cur_varobj.more_children = True
            for child_tup in record.results["children"][:max_children]:
                child = child_tup[1]
                varobj = VariableObjectManager.create_var_obj(child)
                if not varobj:
                    print "Could not create child varobj!"
                    return True
                if not self.varobjs[rank].add_var_obj(varobj):
                    print "Could not add child varobj!"
                    return True
                if int(varobj.num_child) > 0 or varobj.is_dynamic:
                    # Only potentially push if the varobj can have children.
                    do_listing = True
                    if parent_depth > max_depth:
                        # If the depth of the parent of this node is greater than five,
                        # we want to terminate the search of this branch, unless this
                        # node is a pseduo-child, or we want to go deeper on one branch.
                        if branch_name and VariableObjectManager.same_branch(varobj.name, branch_name):
                            if parent_depth > branch_depth and not VariableObjectManager.is_pseudochild(varobj):
                                do_listing = False
                        elif not VariableObjectManager.is_pseudochild(varobj):
                            do_listing = False
                    # Don't list null-pointers.
                    if varobj.vartype and varobj.value and varobj.vartype[-1] == "*":
                        try:
                            if int(varobj.value, 0) == 0:
                                do_listing = False
                        except ValueError: pass
                    # Do not evaluate children further when there's an excessive number.
                    if len(record.results["children"]) > 128:
                        do_listing = False
                    # Add to the stack to list if we meet the requirements.
                    if do_listing:
                        self.varprint_stacks[v_id].append((varobj, parent_depth + 1))
        if not self.varprint_stacks[v_id]:
            to_send = self.varobjs[rank].get_var_obj(name)
            if to_send:
                self.comm.send(GDBMessage(VARPRINT_RES_MSG, varobj = to_send, rank = rank, err = False), self.comm.frontend)
            else:
                self.comm.send(GDBMessage(VARPRINT_RES_MSG, rank = rank, err = True, msg = "Variable does not exist."), self.comm.frontend)
        else:
            to_list, depth = self.varprint_stacks[v_id][-1]
            if reset_maxes:
                def _list_handler(record):
                    return self.varprint_dfs(record, rank, v_id, name, branch_depth = branch_depth,
                                             branch_name = branch_name)
            else:
                def _list_handler(record):
                    return self.varprint_dfs(record, rank, v_id, name, max_depth = max_depth,
                                             max_children = max_children, reset_maxes = reset_maxes,
                                             branch_depth = branch_depth, branch_name = branch_name)
            tokens = self.run_gdb_command(Command("var-list-children", args = ("1", '"' + to_list.name + '"')), rank)
            self.be.add_token_handler(tokens[rank], _list_handler)
