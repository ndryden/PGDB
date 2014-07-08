"""Handles aggregated records."""

import copy
from collections import defaultdict
from mi.gdbmi_parser import *
from mi.gdbmi_records import *
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

    An object is primitive if it is a string, integer, None, or a list of
    primitives.

    """
    return (_is_str(v) or _is_int(v) or (v is None) or
            (_is_list(v) and all([_is_primitive(x) for x in v])))

def combine_records(records, ranks):
    """Combine a list of records into the smallest set of aggregated records.

    records is a list of records.
    ranks is a list of associated ranks, in the same order.
    Returns a list of aggregated records.

    """
    type_dict = defaultdict(list)
    arecs = []
    for record, rank in zip(records, ranks):
        # This is immutable and should identify records of the same type.
        t = tuple([record.record_type] + list(record.record_subtypes))
        type_dict[t].append((rank, record))
    for t in type_dict:
        first_rec = type_dict[t].pop(0)
        arec = GDBMIAggregatedRecord(first_rec[0], first_rec[1])
        for rank, record in type_dict[t]:
            other_arec = GDBMIAggregatedRecord(rank, record)
            arec.merge(other_arec)
        arecs.append(arec)
    return arecs

def combine_aggregated_records(arecs):
    """Combine a list of aggregated records into the smallest such set."""
    type_dict = defaultdict(list)
    new_arecs = []
    for arec in arecs:
        t = tuple([arec.record_type] + list(arec.record_subtypes))
        type_dict[t].append(arec)
    for t in type_dict:
        first_arec = type_dict[t].pop(0)
        for arec in type_dict[t]:
            first_arec.merge(arec)
        new_arecs.append(first_arec)
    return new_arecs

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
          - check whether a different entry should become default
          - if yes, replace default
          - if no, add to other

        """
        if self.default == data:
            # Same as current default: do nothing.
            return
        default_count = len(ranks) - len(self.other)
        _data = data
        if _is_list(_data):
            _data = tuple(_data)
        counter_dict = {_data: 1}
        for v in self.other.values():
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
        my_default = self.default
        other_default = other.default
        if _is_list(my_default):
            my_default = tuple(my_default)
        if _is_list(other_default):
            other_default = tuple(other_default)
        counter_dict = {my_default: my_default_count,
                        other_default: other_default_count}
        for v in self.other.values():
            if _is_list(v):
                # Convert for immutability.
                v = tuple(v)
            if v in counter_dict:
                counter_dict[v] += 1
            else:
                counter_dict[v] = 1
        for v in other.other.values():
            if _is_list(v):
                # Convert for immutability.
                v = tuple(v)
            if v in counter_dict:
                counter_dict[v] += 1
            else:
                counter_dict[v] = 1
        max_value = max(counter_dict.keys(), key=lambda x: counter_dict[x])
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

    def get_substitution(self, rank):
        """Return the substitution for the rank."""
        if rank in self.other:
            return self.other[rank]
        else:
            return self.default

    def __str__(self):
        return "_Substitution: default = {0}\nothers = {1}".format(self.default,
                                                                   self.others)

class GDBMIAggregatedRecord:
    """Aggregated GDBMIRecord making use of substitutions.

    The record has an Interval of all ranks involved in it.

    """

    def __init__(self, rank, record):
        self.init_record(rank, record)

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
        self.ranks = Interval(rank)
        for field in self.fields:
            other_attr = getattr(record, field)
            setattr(self, field, self.create_structure(other_attr))

    def add_record(self, rank, record):
        self.ranks += Interval(rank)
        if ((record.record_type != self.record_type) or
            (record.record_subtypes != self.record_subtypes)):
            raise ValueError(record)
        for field in self.fields:
            self.copy_structure(rank, getattr(self, field),
                                getattr(record, field))
        self.ranks += Interval(rank)

    def merge_recursive(self, field, other_field, other_ranks):
        if isinstance(field, _Substitution):
            field.merge(other_field, self.ranks, other_ranks)
        elif _is_list(field):
            for d1, d2 in zip(field, other_field):
                self.merge_recursive(d1, d2, other_ranks)
        elif _is_dict(field):
            for k in field:
                self.merge_recursive(field[k], other_field[k], other_ranks)

    def merge(self, other):
        if ((self.record_type != other.record_type) or
            (self.record_subtypes != other.record_subtypes)):
            raise ValueError(record)
        for field in self.fields:
            self.merge_recursive(getattr(self, field),
                                 getattr(other, field),
                                 other.ranks)
        self.ranks += other.ranks

    def reconstruct_recursive(self, rank, data):
        if isinstance(data, _Substitution):
            return data.get_substitution(rank)
        elif _is_list(data):
            new_data = []
            for d in data:
                new_data.append(self.reconstruct_recursive(rank, d))
            return new_data
        elif _is_dict(data):
            new_data = {}
            for k in data:
                new_data[k] = self.reconstruct_recursive(rank, data[k])

    def get_record(self, rank):
        """Return the reconstructed record for the given rank."""
        if self.record_type in [ASYNC_EXEC, ASYNC_STATUS, ASYNC_NOTIFY]:
            record = GDBMIAsyncRecord()
        elif self.record_type in [STREAM_CONSOLE, STREAM_TARGET, STREAM_LOG]:
            record = GDBMIStreamRecord()
        elif self.record_type == RESULT:
            record = GDBMIResultRecord()
        else:
            record = GDBMIUnknownRecord()
        record.record_type = self.record_type
        record.record_subtypes = self.record_subtypes
        record.fields = self.fields
        for field in self.fields:
            setattr(record, field,
                    self.reconstruct_recursive(rank, getattr(self, field)))
        return record

    def get_record_classes(self):
        """Get the classes of records in this aggregated record.

        A record class is a set of records that use the same substitutions for
        every field.

        This returns a dictionary indexed by records, containing ranks.

        """
        class_dict = {}
        for rank in self.ranks:
            record = self.get_record(rank)
            if record in class_dict:
                class_dict[record] += Interval(rank)
            else:
                class_dict[record] = Interval(rank)
        return class_dict

    def get_ranks(self):
        return self.ranks

    def __str__(self):
        return "AggregatedRecord({0}, {1})".format(self.record_type,
                                                   self.record_subtypes)
