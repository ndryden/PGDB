"""A simple integer interval representation."""

class Interval(object):
    """Efficiently store and support queries for disjoint integer intervals.

    This uses O(n) memory, less if there are many contiguous intervals, and
    O(logn) to test for membership. Construction takes O(nlogn) for unsorted
    data and O(n) for sorted data.

    This compresses contiguous intervals when possible and uses binary search
    for membership testing.

    """

    def __init__(self, intervals=None, lis=None, is_sorted=False):
        """Initialize the intervals.

        intervals - if present, a list of disjoint intervals as tuples.
        lis - if present, a list of integers to be constructed into intervals.
        is_sorted - whether the aforementioned lists are already sorted or not.
        Note that intervals and lis are mutually exclusive. The entries in these
        should be non-negative.

        """
        if intervals is None and lis is None:
            raise ValueError("Must provide at least one of intervals or lis.")
        if intervals and lis:
            raise ValueError("Cannot provide both intervals and lis.")
        if not is_sorted:
            if intervals:
                intervals.sort(key=lambda x: x[0])
            if lis:
                lis.sort()
        self.intervals = []
        if intervals:
            # Interval compression for existing intervals.
            cur = intervals[0]
            for interval in intervals[1:]:
                if interval[0] == cur[1] + 1:
                    # The intervals are contiguous.
                    cur = (cur[0], interval[1])
                else:
                    # Not contiguous, store cur.
                    self.intervals.append(cur)
                    cur = interval
            # Append the last interval.
            self.intervals.append(cur)
        elif lis:
            # Construct compressed intervals from lis.
            cur_min = lis[0]
            cur_max = lis[0]
            for i in lis[1:]:
                if i == cur_max + 1:
                    # We have another contiguous integer.
                    # Add it to the current interval.
                    cur_max += 1
                else:
                    # Not contiguous, store the present interval and start anew.
                    self.intervals.append((cur_min, cur_max))
                    cur_min = i
                    cur_max = i
            # Append the last interval.
            self.intervals.append((cur_min, cur_max))

    def _binary_search_intervals(self, i):
        """Return the index of the interval that contains i, if any.

        This uses a binary search over the intervals.

        """
        low = 0
        high = len(self.intervals)
        while low < high:
            mid = (low + high) // 2
            v = self.intervals[mid]
            if i < v[0]:
                high = mid
            elif i > v[1]:
                low = mid + 1
            else:
                return mid
        return None

    @staticmethod
    def _interval_intersect(intv1, intv2):
        """Return the intersection of intervals intv1 and intv2.

        intv1 and intv2 should be tuples of the form (low, high).

        """
        if intv1[0] <= intv2[1] and intv2[0] <= intv1[1]:
            # The intervals have a non-empty intersection.
            return (max(intv1[0], intv2[0]), min(intv1[1], intv2[1]))
        else:
            return None

    @staticmethod
    def _interval_difference(intv1, intv2):
        """Return the difference of intervals intv1 and intv2.

        intv1 and intv2 should be tuples of the form (low, high).

        """
        if intv1[0] <= intv2[1] and intv2[0] <= intv1[1]:
            # We have a non-empty intersection.
            if intv1[0] < intv2[0]:
                if intv1[1] <= intv2[1]:
                    return [(intv1[0], intv2[0] - 1)]
                else:
                    return [(intv1[0], intv2[0] - 1), (intv2[1] + 1, intv1[1])]
            elif intv2[0] < intv1[0]:
                if intv1[1] <= intv2[1]:
                    return None
                else:
                    return [(intv2[1] + 1, intv1[1])]
            elif intv2[1] < intv1[1]:
                return [(intv2[1] + 1, intv1[1])]
            else:
                return None
        else:
            return [intv1]

    @staticmethod
    def _union_intersecting_intervals(intv1, intv2):
        """Return the union of two intersecting intervals."""
        return (min(intv1[0], intv2[0]), max(intv1[1], intv2[1]))

    def in_interval(self, i):
        """Check if an integer i is in one of the intervals here.

        This does a binary search of the intervals.

        """
        if self._binary_search_intervals(i) is not None:
            return True
        return False

    def get_smallest(self):
        """Return the smallest value in the interval."""
        return self.intervals[0][0]

    def get_largest(self):
        """Return the largest value in the interval."""
        return self.intervals[-1][1]

    def members(self):
        """A generator of every integer in the intervals."""
        if not self.intervals:
            return
        cur_intv = 0
        cur_i = self.intervals[cur_intv][0]
        while True:
            yield cur_i
            cur_i += 1
            if cur_i > self.intervals[cur_intv][1]:
                cur_intv += 1
                if cur_intv >= len(self.intervals):
                    break
                cur_i = self.intervals[cur_intv][0]

    def intersect(self, other):
        """Return the intersection of this interval with the given interval.

        This takes O(n) time.

        """
        if not len(other):
            return Interval(lis=[], is_sorted=True)
        k = 0
        intersection = []
        for interval in self.intervals:
            while k < len(other):
                intersect = self._interval_intersect(interval,
                                                     other.intervals[k])
                if intersect:
                    intersection.append(intersect)
                    if other.intervals[k][1] <= interval[1]:
                        k += 1
                    else:
                        break
                else:
                    if other.intervals[k][1] < interval[0]:
                        k += 1
                    else:
                        break
        return Interval(intervals=intersection, is_sorted=True)

    def intersect_list(self, lis):
        """Return a list of items that are in both the list and this interval.

        Takes O(klogn) time where k = len(lis).

        """
        intersection = []
        for i in lis:
            if self.in_interval(i):
                intersection.append(i)
        return intersection

    def union(self, other):
        """Return the union of this interval with the given interval.

        This takes O(n) time.

        """
        if not len(other):
            return self.intervals
        if not len(self):
            return Interval(lis=[], is_sorted=True)
        i = 1
        k = 0
        new = []
        cur = self.intervals[0]
        while i < len(self) or k < len(other):
            pasti = False
            pastk = False
            if i < len(self):
                interval = self.intervals[i]
                if self._interval_intersect(interval, cur):
                    # Extend the current interval and advance.
                    cur = self._union_intersecting_intervals(interval, cur)
                    i += 1
                else:
                    if interval[1] < cur[0]:
                        # We're before the current interval.
                        new.append(interval)
                        i += 1
                    else:
                        # We're past the current interval.
                        pasti = True
            else:
                pasti = True
            if k < len(other):
                interval = other.intervals[k]
                if self._interval_intersect(interval, cur):
                    # Extend and advance.
                    cur = self._union_intersecting_intervals(interval, cur)
                    k += 1
                else:
                    if interval[1] < cur[0]:
                        # Before current interval.
                        new.append(interval)
                        k += 1
                    else:
                        # Past the current interval.
                        pastk = True
            else:
                pastk = True
            if pasti and pastk:
                new.append(cur)
                if i < len(self):
                    cur = self.intervals[i]
                elif k < len(other):
                    cur = other.intervals[k]
            elif i == len(self) and k == len(other):
                new.append(cur)
        return Interval(intervals=new, is_sorted=True)

    def difference(self, other):
        """Return the set-theoretic difference of this interval with other.

        This takes O(n) time.

        """
        if not len(other):
            return self
        k = 0
        new = []
        for interval in self.intervals:
            append = False
            while k < len(other):
                if self._interval_intersect(interval, other.intervals[k]):
                    append = True
                    diff = self._interval_difference(interval,
                                                     other.intervals[k])
                    if diff:
                        new += diff
                        if other.intervals[k][1] <= interval[1]:
                            k += 1
                        else:
                            break
                    else:
                        k += 1
                else:
                    if other.intervals[k][0] > interval[1] and not append:
                        append = True
                        new.append(interval)
                        k += 1
                        break
                    k += 1
            if k >= len(other) and not append:
                new.append(interval)
        return Interval(intervals=new, is_sorted=True)

    def symmetric_difference(self, other):
        """Return the symmetric difference of this interval with other.

        This takes O(n) time.

        """
        # This is equivalent to symmetric difference.
        return self.union(other).difference(self.intersect(other))

    def range(self):
        """Return the interval from the left to the right side of this interval.

        More specifically, if this consists of {[x1,x'1],...,[xn,x'n]}, we
        return {[x1,x'n]}.

        """
        return Interval(intervals=[(self.intervals[0][0],
                                    self.intervals[-1][1])],
                        is_sorted=True)

    def empty(self):
        """Return whether this interval is empty or not."""
        return len(self.intervals) == 0

    def count(self):
        """Return the number of elements that this interval represents."""
        num = 0
        for tup in self.intervals:
            num += tup[1] - tup[0] + 1
        return num

    def __contains__(self, i):
        """Invoke in_interval."""
        return self.in_interval(i)

    def __len__(self):
        """Return the number of intervals stored in this interval."""
        return len(self.intervals)

    def __eq__(self, other):
        """Return true if two intervals are precisely the same."""
        if not isinstance(other, Interval):
            return NotImplemented
        return all([x == y for x, y in zip(self.intervals, other.intervals)])

    def __ne__(self, other):
        """Return the negation of what __eq__ returns."""
        return not self.__eq__(other)

    def __hash__(self):
        """Return a hash for this set."""
        if not self.intervals:
            return hash(None)
        cur_hash = hash(self.intervals[0])
        for interval in self.intervals[1:]:
            cur_hash ^= hash(interval)
        return cur_hash

    def __str__(self):
        """Get a string representation of the set."""
        string = ""
        for i in self.intervals:
            if i[0] == i[1]:
                string += "{0},".format(i[0])
            else:
                string += "{0}-{1},".format(i[0], i[1])
        return string[:-1]

    def __repr__(self):
        """Get a raw representation of the set."""
        return repr(self.intervals)

    def __iter__(self):
        """Get an iterator for this set."""
        return self.members()

    def __add__(self, other):
        """Return the union of this set and other."""
        if not isinstance(other, Interval):
            return NotImplemented
        return self.union(other)

    def __sub__(self, other):
        """Return the set-theoretic difference of this set and other."""
        if not isinstance(other, Interval):
            return NotImplemented
        return self.difference(other)

    def __and__(self, other):
        """Return the intersection of this set and other."""
        if isinstance(other, Interval):
            return self.intersect(other)
        elif isinstance(other, list):
            return self.intersect_list(other)
        return NotImplemented

    def __xor__(self, other):
        """Return the symmetric difference of this set and other."""
        if not isinstance(other, Interval):
            return NotImplemented
        return self.symmetric_difference(other)
