"""Management classes for GDB variable objects.

These maintain a hierarchy of the variable objects and associated information, but must be maintained
externally.

"""

import re

DISPLAY_HINT_STRING = "string"
DISPLAY_HINT_ARRAY = "array"
DISPLAY_HINT_MAP = "map"

class VariableObject:
    """A variable object.

    This stores the associated data for the variable object, plus any children.

    """

    def __init__(self, name, vartype, value = None, thread_id = None,
                 display_hint = None, is_dynamic = False, has_more = False, num_child = 0):
        """Initialize the variable object."""
        self.name = name
        self.vartype = vartype
        self.value = value
        self.children = {}
        self.thread_id = thread_id
        self.display_hint = display_hint
        self.is_dynamic = is_dynamic
        self.has_more = has_more
        self.num_child = num_child
        self.listed = False
        self.more_children = False

    def get_parent(self):
        """Return the name of the parent of this variable object."""
        name_parts = self.name.split(".")
        if len(name_parts) > 1:
            return ".".join(name_parts[0:-1])
        # No parent.
        return None

    def get_name(self):
        """Return the shortened name of this variable object."""
        return self.name.split(".")[-1]

    def get_sorted_children(self):
        """Return the children of this variable object, sorted intelligently.

        This looks to determine whether the childrens' names are keys, and sorts based on the integer
        value of the keys; otherwise it uses a standard comparison based on names.

        """
        if not self.children:
            return []
        name_sample = self.children.values()[0].get_name()
        if re.match(r"\[[0-9]+\]", name_sample):
            # We can sort these, assume they're all the same.
            children = sorted(self.children.items(), key = lambda x: int(x[1].get_name()[1:-1]))
            return children
        else:
            # Cannot easily sort, so just use the standard comparison.
            return sorted(self.children.items(), key = lambda x: x[1].get_name())

    def __str__(self):
        """Return the name of the variable object."""
        return self.get_name()

    def __repr__(self):
        """Return the name of the variable object."""
        return self.get_name()

class VariableObjectManager:
    """A top-level manager for variable objects."""
    pseudochildren = ["public", "protected", "private"]

    def __init__(self):
        """Initialization."""
        self.varobjs = {}

    def get_child(self, varobj, name):
        """A helper function to get the child of a variable object based on a name.

        This examines the children of the given variable object and searches for one with the given
        name (this is the short name). This also examines the children of any pseudochildren the
        varobj has.

        """
        if name in varobj.children:
            return varobj.children[name]
        else:
            # If it's not present, check our pseduo-children, if any.
            if "public" in varobj.children and name in varobj.children["public"].children:
                return varobj.children["public"].children[name]
            elif "protected" in varobj.children and name in varobj.children["protected"].children:
                return varobj.children["protected"].children[name]
            elif "private" in varobj.children and name in varobj.children["private"].children:
                return varobj.children["private"].children[name]
            else:
                return None # Not present at all.

    def get_var_obj(self, name):
        """Get a variable object based on a name."""
        name_parts = name.split(".")
        if len(name_parts) == 1:
            if name in self.varobjs:
                return self.varobjs[name]
            return None
        if name_parts[0] not in self.varobjs:
            return None
        varobj = self.varobjs[name_parts[0]]
        for part in name_parts[1:]:
            varobj = self.get_child(varobj, part)
            if varobj is None:
                return None
        return varobj

    def add_var_obj(self, newvarobj):
        """Add a variable object to the manager."""
        name_parts = newvarobj.name.split(".")
        if len(name_parts) == 1:
            self.varobjs[newvarobj.name] = newvarobj
            return True
        parent = self.get_var_obj(".".join(name_parts[:-1]))
        if parent:
            parent.children[name_parts[-1]] = newvarobj
            return True
        return False

    def del_var_obj(self, varobj):
        """Remove a variable object from the manager."""
        name_parts = varobj.name.split(".")
        if len(name_parts) == 1:
            del self.varobjs[varobj.name]
            return True
        parent = self.get_var_obj(".".join(name_parts[:-1]))
        if parent:
            del parent.children[name_parts[-1]]
            return True
        return False

    def get_lowest_ancestor(self, name):
        """Get the lowest ancestor of a name that the manager has a variable object for."""
        name_parts = name.split(".")
        if name_parts[0] not in self.varobjs:
            return None
        varobj = self.varobjs[name_parts[0]]
        for part in name_parts[1:]:
            child = self.get_child(varobj, part)
            if child is None:
                return varobj
            varobj = child
        return varobj

    def get_full_name(self, name):
        """Get the full name from a provided name, including the pseudochildren in the name."""
        full_name = ""
        name_parts = name.split(".")
        if name_parts[0] not in self.varobjs:
            return None
        full_name += name_parts[0]
        varobj = self.varobjs[name_parts[0]]
        for part in name_parts[1:]:
            if part in varobj.children:
                full_name += "." + part
                varobj = varobj.children[part]
            else:
                # Check the pseduo-children.
                if "public" in varobj.children and part in varobj.children["public"].children:
                    full_name += ".public." + part
                    varobj = varobj.children["public"].children[part]
                elif "protected" in varobj.children and part in varobj.children["protected"].children:
                    full_name += ".protected." + part
                    varobj = varobj.children["protected"].children[part]
                elif "private" in varobj.children and part in varobj.children["private"].children:
                    full_name += ".private." + part
                    varobj = varobj.children["private"].children[part]
                else:
                    return None # Not present at all.
        return full_name

    @staticmethod
    def get_name_depth(name):
        """Get the depth of a name."""
        return len(name.split("."))

    @staticmethod
    def get_base_name(name):
        """Get the root of a variable object's name."""
        return name.split(".")[0]

    @staticmethod
    def same_branch(name1, name2):
        """Return whether two names are on the same branch of the variable object tree."""
        def _name_filter(part):
            return part not in VariableObjectManager.pseudochildren
        name1_split = filter(_name_filter, name1.split("."))
        name2_split = filter(_name_filter, name2.split("."))
        branch = zip(name1_split, name2_split)
        return all(map(lambda x: x[0] == x[1], branch))

    @staticmethod
    def is_pseudochild(varobj):
        """Return whether a variable object is a pseudochild."""
        return varobj.get_name() in VariableObjectManager.pseudochildren

    @staticmethod
    def create_var_obj(var):
        """Create a new variable object based on entries from a record."""
        if "name" not in var:
            return False
        if "type" in var:
            vartype = var["type"]
            if "value" in var:
                value = var["value"]
            else:
                value = None
        else:
            vartype = None
            value = None
        if "displayhint" in var:
            displayhint = var["displayhint"]
        else:
            displayhint = None
        if "dynamic" in var:
            dynamic = var["dynamic"]
        else:
            dynamic = False
        if "thread-id" in var:
            thread_id = var["thread-id"]
        else:
            thread_id = None
        return VariableObject(var["name"], vartype, value = value,
                              thread_id = thread_id,
                              display_hint = displayhint,
                              is_dynamic = dynamic, num_child = var["numchild"])
    
    def print_hierarchy(self, children = None, indent = 0):
        """Debug function to print the hierarchy of variable objects."""
        if children is None:
            children = self.varobjs
        print ("  " * indent) + str(children)
        for child in children.values():
            self.print_hierarchy(child.children, indent = indent + 1)
