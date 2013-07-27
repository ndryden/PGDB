"""Handles aggregated records."""

import copy
from mi.gdbmi_parser import *
from mi.gdbmi_identifier import GDBMIRecordIdentifier
from interval import Interval

identifier = GDBMIRecordIdentifier()

class Substitution:
    """Class for managing substitutions for records."""

    def __init__(self):
        self.substitutions = {}
        self.cur_subst_key = 0
        self.ids = None

    def _next_key(self):
        """Return the next usable key."""
        key = self.cur_subst_key
        self.cur_subst_key += 1
        return key

    def add_substitution(self, value, vid):
        """Add value as a new substitution and return a new key."""
        key = self._next_key()
        # We have only one data point, so it is clearly the default.
        self.substitutions[key] = (value, {})
        if not self.ids:
            self.ids = Interval(lis = [vid], is_sorted = True)
        elif vid not in self.ids:
            self.ids += Interval(lis = [vid], is_sorted = True)
        return key

    def get_num_substitutions(self):
        """Return the number of substitutions present."""
        return len(self.substitutions)

    def get_all_substitution(self, key):
        """Get all the values associated with a key."""
        return [self.substitutions[key][0]] + self.substitutions[key][1].values()

    def get_substitution(self, key, vid):
        """Get the value associated with a key and a VID."""
        if vid in self.substitutions[key][1]:
            return self.substitutions[key][1][vid]
        return self.substitutions[key][0]

    def get_substitutions_for_vid(self, vid):
        """Get the set of substitution values for a vid."""
        substs = {}
        for k in self.substitutions:
            if vid in self.substitutions[k][1]:
                substs[k] = self.substitutions[k][1][vid]
            else:
                substs[k] = self.substitutions[k][0]
        return substs

    def get_substitution_classes(self):
        """Get the sets of VIDs that have the same set of substitutions."""
        subst_classes = {}
        for vid in self.ids:
            # Convert to a string to be immutable.
            subst = repr(self.get_substitutions_for_vid(vid))
            if subst in subst_classes:
                subst_classes[subst].append(vid)
            else:
                subst_classes[subst] = [vid]
        return subst_classes.values()

    def get_ids(self):
        """Return the interval of IDs for which this is a substitution."""
        return self.ids

    def add_id(self, vid):
        """Add an ID to the substitution."""
        if not self.ids:
            self.ids = Interval(lis = [vid], is_sorted = True)
        elif vid not in self.ids:
            self.ids += Interval(lis = [vid], is_sorted = True)

    def merge_substitution(self, other, my_key, other_key):
        """Merge the substitution referred to by my_key and other_key together.

        This will construct a new tuple value for insertion.
        Note that the set of ids for the main structure will need to be updated
        by a separate process.

        Returns the new (default, dict) value to be used for this substitution.

        """
        my_old_default = self.substitutions[my_key][0]
        my_old_dict = self.substitutions[my_key][1]
        other_old_default = other.substitutions[other_key][0]
        other_old_dict = other.substitutions[other_key][1]
        counter_dict = {}
        num_my_ids = len(self.ids)
        num_other_ids = len(other.ids)
        total_num_ids = num_my_ids + num_other_ids
        my_dict_count = len(my_old_dict)
        other_dict_count = len(other_old_dict)
        my_default_count = num_my_ids - my_dict_count
        other_default_count = num_other_ids - other_dict_count

        # Compute the counts of values in the old dicts.
        for v in my_old_dict.itervalues():
            d = v
            if _is_list(v):
                # Convert to tuple for immutability.
                d = tuple(v)
            if d in counter_dict:
                counter_dict[d] += 1
            else:
                counter_dict[d] = 1
        for v in other_old_dict.itervalues():
            d = v
            if _is_list(v):
                # Convert to tuple for immutability.
                d = tuple(v)
            if d in counter_dict:
                counter_dict[d] += 1
            else:
                counter_dict[d] = 1
        # Catch if there are no non-default entries.
        if not counter_dict:
            # Need to merge defaults. Keep as default the one with more IDs.
            if my_old_default == other_old_default:
                # If both defaults are the same, we don't have to do anything.
                return (my_old_default, my_old_dict)
            elif my_default_count >= other_default_count:
                # Mine has more or the same number of IDs.
                for vid in other.ids:
                    my_old_dict[vid] = other_old_default
                return (my_old_default, my_old_dict)
            else:
                # Other has more IDs.
                for vid in self.ids:
                    my_old_dict[vid] = my_old_default
                return (other_old_default, my_old_dict)
        # Compute the value that has the maximum number of appearances.
        max_value = max(counter_dict.iterkeys(), key = lambda x: counter_dict[x])
        max_count = counter_dict[max_value]

        # Determine what needs to change.
        new_default = None
        new_dict = {}
        if my_old_default == other_old_default:
            if max_count > (my_default_count + other_default_count):
                # Both defaults are the same, but some value exceeds them.
                # Replace old default with this new value.
                new_default = max_value
                # Move old non-max values to new dict.
                for k, v in my_old_dict.iteritems():
                    if v != max_value:
                        new_dict[k] = v
                for k, v in other_old_dict.iteritems():
                    if v != max_value:
                        new_dict[k] = v
                # Move old defaults to new dict.
                for vid in self.ids:
                    if vid not in my_old_dict:
                        new_dict[vid] = my_old_default
                for vid in other.ids:
                    if vid not in other_old_dict:
                        new_dict[vid] = other_old_default
            else:
                # No change to defaults. Set new default to be old default.
                new_default = my_old_default
                # Move old dicts to new dict.
                new_dict = dict(list(my_old_dict.items()) + list(other_old_dict.items()))
        else:
            # My default and other default differ.
            if my_default_count > other_default_count:
                if max_count > my_default_count:
                    # Some value exceeds the maximum default.
                    # Replace old default with this new value.
                    new_default = max_value
                    # Move old non-max values to new dict.
                    for k, v in my_old_dict.iteritems():
                        if v != max_value:
                            new_dict[k] = v
                    for k, v in other_old_dict.iteritems():
                        if v != max_value:
                            new_dict[k] = v
                    # Move old defaults into new dict.
                    for vid in self.ids:
                        if vid not in my_old_dict:
                            new_dict[vid] = my_old_default
                    for vid in other.ids:
                        if vid not in other_old_dict:
                            new_dict[vid] = other_old_default
                else:
                    # My default is max and exceeds other default.
                    # Set new default to be old default.
                    new_default = my_old_default
                    # Move old dicts to new dict.
                    new_dict = dict(list(my_old_dict.items()) + list(other_old_dict.items()))
                    # Move other default into new dict.
                    for vid in other.ids:
                        if vid not in other_old_dict:
                            new_dict[vid] = other_old_default
            else:
                if max_count > other_default_count:
                    # Some value exceeds maximum default.
                    # Replace old default with this new value.
                    new_default = max_value
                    # Move old non-max values to new dict.
                    for k, v in my_old_dict.iteritems():
                        if v != max_value:
                            new_dict[k] = v
                    for k, v in other_old_dict.iteritems():
                        if v != max_value:
                            new_dict[k] = v
                    # Move old defaults into new dict.
                    for vid in self.ids:
                        if vid not in my_old_dict:
                            new_dict[vid] = my_old_default
                    for vid in other.ids:
                        if vid not in other_old_dict:
                            new_dict[vid] = other_old_default
                else:
                    # Other default is max and exceeds my default.
                    # Set new default to be old default.
                    new_default = other_old_default
                    # Move old dicts to new dict.
                    new_dict = dict(list(my_old_dict.items()) + list(other_old_dict.items()))
                    # Move my default into new dict.
                    for vid in self.ids:
                        if vid not in my_old_dict:
                            new_dict[vid] = my_old_default
        # This is a final passthrough to update the dict in the case that there are
        # default values in it.
        keys_to_del = []
        for k, v in new_dict.iteritems():
            if v == new_default:
                keys_to_del.append(k)
        for k in keys_to_del:
            del new_dict[k]
        return (new_default, new_dict)

    def combine_substitutions(self, other, key_map = None):
        """Given this and another Substitution object, combine their substitutions.

        key_map gives a mapping from the keys of this Substition to those in other.
        If it is not provided, the identity map is used.
        This assumes that the two Substitutions are for the same structure.

        """
        if not key_map:
            key_map = dict(zip(self.substitutions.keys(), self.substitutions.keys()))
        # Merge substitutions.
        new_substitutions = {}
        for k in self.substitutions:
            new_substitutions[k] = self.merge_substitution(other, k, key_map[k])
        self.substitutions = new_substitutions
        # Update the set of ids.
        self.ids += other.ids

    def __str__(self):
        """Return a string representation of this substitution."""
        return "Substitution: ids = {0}, substitutions = {1}".format(self.ids, self.substitutions)

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
    return _is_str(v) or (_is_list(v) and all(map(lambda x: _is_str(x), v))) or (_is_tuple(v) and all(map(lambda x: _is_str(x), v)))

def _is_subst_key(v):
    """Check whether an object is a substitution key.

    A substitution key is an integer.

    """
    return _is_int(v)

def _do_substitution(vid, data, subst):
    """Recursive helper for doing substitutions."""
    if _is_primitive(data):
        k = subst.add_substitution(data, vid)
        return k, subst
    if _is_list(data):
        for k, v in enumerate(data):
            new_v, subst = _do_substitution(vid, v, subst)
            data[k] = new_v
        return data, subst
    if _is_tuple(data):
        # Convert to list and back to tuple so we can modify.
        tmp_data = list(data)
        for k, v in enumerate(tmp_data):
            new_v, subst = _do_substitution(vid, v, subst)
            tmp_data[k] = new_v
        return tuple(tmp_data), subst
    if _is_dict(data):
        for k, v in list(data.items()):
            new_v, subst = _do_substitution(vid, v, subst)
            data[k] = new_v
        return data, subst
    return None, None

def _undo_substitution(vid, data, subst):
    """Recursive helper for undoing substitutions."""
    if _is_subst_key(data):
        return subst.get_substitution(data, vid)
    if _is_list(data):
        for k, v in enumerate(data):
            new_v = _undo_substitution(vid, v, subst)
            data[k] = new_v
        return data
    if _is_tuple(data):
        tmp_data = list(data)
        for k, v in enumerate(tmp_data):
            new_v = _undo_substitution(vid, v, subst)
            tmp_data[k] = new_v
        return tuple(tmp_data)
    if _is_dict(data):
        for k, v in list(data.items()):
            new_v = _undo_substitution(vid, v, subst)
            data[k] = new_v
        return data
    return data

def _aggregate_record(record, vid):
    """Given a record, construct a Substitution for it.

    This creates a new record with the relevant substitution keys filled in
    and the corresponding Substitution structure.

    Substitution is performed as follows.
    Primitive values are strings or lists of strings.
    Primitive values are fully substituted.
    Lists which are not primitive have each element recursively substituted.
    Dictionaries have each element recursively substituted.

    """
    data = None
    if record.record_type == RESULT:
        data = record.results
    elif record.record_type in [ASYNC_EXEC, ASYNC_STATUS, ASYNC_NOTIFY]:
        data = record.output
    elif record.record_type in [STREAM_CONSOLE, STREAM_TARGET, STREAM_LOG]:
        data = record.string
    else:
        return None, None
    subst = Substitution()
    data, subst = _do_substitution(vid, data, subst)
    if record.record_type == RESULT:
        record.results = data
    elif record.record_type in [ASYNC_EXEC, ASYNC_STATUS, ASYNC_NOTIFY]:
        record.output = data
    elif record.record_type in [STREAM_CONSOLE, STREAM_TARGET, STREAM_LOG]:
        record.string = data
    # Catch for things that have no data.
    if len(subst.substitutions) == 0:
        subst.add_id(vid)
    return record, subst

def combine_aggregations(arec1, arec2):
    """Given two aggregations of messages of the same type, combine them.

    This presently assumes that the entries in the messages are in the same
    order; in particular, that iterating over dictionaries in both messages
    is done in the same order.

    This returns a new aggregated record.

    """
    arec1.substitutions.combine_substitutions(arec2.substitutions)
    return arec1

def combine_aggregation_lists(l1, l2):
    """Given two lists of aggregated records, combine aggregations of the same type.

    Note that it is assumed that each list contains at most one of each type of
    record, per the identifier.

    """
    type_dict = {}
    for v in l1:
        # Convert to tuple for immutability.
        type_dict[tuple(identifier.identify(v.record))] = v
    l = []
    for v in l2:
        ident = tuple(identifier.identify(v.record))
        # The number of substitutions must be the same.
        # Note that this can differ even among records that are identified as the same type.
        # E.g., stops in functions with different numbers of arguments.
        # Note that there may still be errors due to keys being in different orders.
        if (ident in type_dict) and (v.substitutions.get_num_substitutions() == type_dict[ident].substitutions.get_num_substitutions()):
            l.append(combine_aggregations(type_dict[ident], v))
            del type_dict[ident]
        else:
            l.append(v)
    for v in type_dict.itervalues():
        l.append(v)
    return l

class GDBMIAggregatedRecord:
    """Aggregated GDBMIRecord making use of substitutions."""

    def __init__(self, record, vid):
        """Initialization."""
        self.record, self.substitutions = _aggregate_record(record, vid)

    def get_record(self, vid):
        """Return a substituted-in version of the record for the given VID."""
        rec = copy.deepcopy(self.record)
        if rec.record_type == RESULT:
            rec.results = _undo_substitution(vid, rec.results, self.substitutions)
        elif rec.record_type in [ASYNC_EXEC, ASYNC_STATUS, ASYNC_NOTIFY]:
            rec.output = _undo_substitution(vid, rec.output, self.substitutions)
        elif rec.record_type in [STREAM_CONSOLE, STREAM_TARGET, STREAM_LOG]:
            rec.string = _undo_substitution(vid, rec.string, self.substitutions)
        return rec

    def get_ids(self):
        """Return the interval of IDs associated with this record."""
        return self.substitutions.get_ids()

    def get_substitution_classes(self):
        """Return the substitution classes."""
        return self.substitutions.get_substitution_classes()

    def __str__(self):
        """Return a string representation of this aggregated record."""
        return "GDBMIAggregatedRecord: record = [{0}], substitutions = [{1}]".format(self.record, self.substitutions)
