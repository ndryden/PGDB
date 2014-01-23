"""Handles aggregated records."""

import copy
from mi.gdbmi_parser import *
from mi.gdbmi_identifier import GDBMIRecordIdentifier
from interval import Interval

def _is_dict(v):
    """Check whether an object is a dictionary."""
    return isinstance(v, dict)

def _is_list(v):
    """Check whether an object is a list."""
    return isinstance(v, list)

def _is_tuple(v):
    """Check whether an object is a tuple."""
    return isinstance(v, tuple)

def _is_str(v):
    """Check whether an object is a string."""
    return isinstance(v, str)

def _is_int(v):
    """Check whether an object is an integer."""
    return isinstance(v, int)

def _is_primitive(v):
    """Check whether an object is a primitive.

    An object is primitive if it is a string or list of strings.

    """
    return _is_str(v) or (_is_list(v) and all(map(_is_str, v)))

class _Substitution:
    """Substitution for aggregated records.

    This stores substitutions using the following system:
    - A default value, which is the value taken by the majority of the records.
    - The remaining values, stored in a dictionary indexed by rank.

    The record that stores this will have an Interval of all ranks. This is
    passed in as needed.

    """

    def __init__(self, data):
        """Initialize the substitution, with initial data."""
        self.default = data
        self.other = {}

    def add(self, data, rank, ranks):
        """Add an entry to the substitution.

        Cases:
        - data is the same as current default: do nothing
        - data differs:
          - check whether this causes a different entry to become the new default
          - if yes, replace default
          - if no, add to other

        """
        if self.default == data:
            # Same as current default: do nothing.
            return
        default_count = len(ranks) - len(self.other)
        counter_dict = {data: 1}
        for v in self.other.itervalues():
            if _is_list(v):
                v = tuple(v)
            if v in counter_dict:
                counter_dict[v] += 1
            else:
                counter_dict[v] = 1
        # We know that data is the only thing that could cause a change.
        max_count = counter_dict[data]
        if default_count >= max_count:
            # No change to default.
            self.other[rank] = data
        else:
            # Replace default with data.
            new_other = {}
            for r in ranks:
                if r not in self.other:
                    new_other[r] = self.default
                else:
                    if self.other[r] != data:
                        new_other[r] = self.other[r]
            self.default = data
            self.other = new_other

    def merge(self, other, my_ranks, other_ranks):
        """Merge other substitution into this one.

        To keep things simple, this presently just does a full rebuild.

        """
        my_default_count = len(my_ranks) - len(self.other)
        other_default_count = len(other_ranks) - len(other.other)
        counter_dict = {self.default: my_default_count,
                        other.default: other_default_count}
        for v in self.other.itervalues():
            if _is_list(v):
                # Convert for immutability.
                v = tuple(v)
            if v in counter_dict:
                counter_dict[v] += 1
            else:
                counter_dict[v] = 1
        for v in other.other.itervalues():
            if _is_list(v):
                # Convert for immutability.
                v = tuple(v)
            if v in counter_dict:
                counter_dict[v] += 1
            else:
                counter_dict[v] = 1
        max_value = max(counter_dict.iterkeys(), key = lambda x: counter_dict[x])
        max_count = counter_dict[max_value]
        new_other = {}
        for r in my_ranks:
            if r in self.other:
                if self.other[r] != max_value:
                    new_other[r] = self.other[r]
            else:
                new_other[r] = self.default
        for r in other_ranks:
            if r in other.other:
                if other.other[r] != max_value:
                    new_other[r] = other.other[r]
            else:
                new_other[r] = other.default
        self.default = max_value
        self.other = new_other


class GDBMIAggregatedRecord:
    """Aggregated GDBMIRecord making use of substitutions.

    The record has an Interval of all ranks involved in it.

    """

    def __init__(self):
        pass

    def create_structure(self, data):
        """Return a structure based upon data.

        If data is a primitive type, use it.
        If data is a non-primitive list, return a list with the entries filled
        in according to their individual types.
        If the data is a dictionary, return a dictionary with the same keys and
        values filled in according to their individual types.
        If the data is an object (GDBMIFrame/Breakpoint/Thread), return an
        instance.

        This sets up the initial substitution structure as well.

        """
        if _is_primitive(data):
            return _Substitution(data)
        if _is_list(data):
            struct = []
            for d in data:
                if _is_primitive(data):
                    struct.append(_Substitution(d))
                else:
                    struct.append(self.create_structure(d))
            return struct
        if _is_dict(data):
            struct = {}
            for k, v in data.items():
                if _is_primitive(v):
                    struct[k] = _Substitution(v)
                else:
                    struct[k] = self.create_structure(v)
            return struct
        if isinstance(data, GDBMIFrame):
            return _Substitution(copy.copy(data))
        if isinstance(data, GDBMIBreakpoint):
            return _Substitution(copy.copy(data))
        if isinstance(data, GDBMIThread):
            return _Substitution(copy.copy(data))
        raise ValueError(data)

    def copy_structure(self, rank, field, data):
        if isinstance(field, _Subsitution):
            field.add(data, rank, self.ranks)
        elif _is_list(field):
            for d1, d2 in zip(field, data):
                copy_structure(rank, d1, d2, False)
        elif _is_dict(field):
            for k in field:
                copy_structure(rank, field[k], data[k], False)

    def init_record(self, rank, record):
        self.record_type = record.record_type
        self.record_subtypes = record.record_subtypes
        self.fields = record.fields
        self.ranks = Interval(lis = [rank], is_sorted = True)
        for field in self.fields:
            other_attr = getattr(record, field)
            setattr(self, '_' + field, self.create_structure(other_attr))

    def add_record(self, rank, record):
        self.ranks += Interval(lis = [rank], is_sorted = True)
        if ((record.record_type != self.record_type) or
            (record.record_subtypes != self.record_subtypes)):
            raise ValueError(record)
        for field in self.fields:
            self.copy_structure(rank, getattr(self, field),
                                getattr(record, field))

    def merge_recursive(self, field, other_field, other_ranks):
        if isinstance(field, _Substitution):
            field.merge(other, self.ranks, other_ranks)
        elif _is_list(field):
            for d1, d2 in zip(field, other_field):
                merge_recursive(d1, d2, other_ranks)
        elif _is_dict(field):
            for k in field:
                merge_recursive(field[k], other_field[k], other_ranks)

    def merge(self, other):
        if ((self.record_type != other.record_type) or
            (self.record_subtypes != other.record_subtypes)):
            raise ValueError(record)
        for field in self.fields:
            self.merge_recursive(getattr(self, field),
                                 getattr(other, field),
                                 other.ranks)
