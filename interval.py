"""A simple integer interval representation."""

class Interval(object):
    """A class to efficiently store and support membership queries for disjoint integer intervals.

    This uses O(n) memory, less if there are many contiguous intervals, and O(logn)
    to test for membership. Construction takes O(nlogn) for unsorted data and O(n) for sorted data.

    This compresses contiguous intervals when possible and uses binary search for membership testing.

    """

    def __init__(self, intervals = None, lis = None, is_sorted = False):
        """Initialize the intervals.

        intervals - if present, is a list of disjoint intervals represented as tuples.
        lis - if present, is a list of integers to be constructed into intervals.
        is_sorted - whether the aforementioned lists are already sorted or not.
        Note that intervals and lis are mutually exclusive.

        """
        if intervals is None and lis is None:
            raise ValueError("Must provide at least one of intervals or lis.")
        if intervals and lis:
            raise ValueError("Cannot provide both intervals and lis.")
        if not is_sorted:
            if intervals:
                intervals.sort(key = lambda x: x[0])
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
                    # We have another contiguous integer, add it to the interval.
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

    def in_interval(self, i):
        """Check if an integer i is in one of the intervals here.

        This does a binary search of the intervals.

        """
        if self._binary_search_intervals(i) is not None:
            return True
        return False

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

    def intersect(self, interval):
        """Return the intersection of this interval with the given interval."""
        raise NotImplemented

    def intersect_list(self, lis):
        """Return a list of items that are in both the list and this interval.

        Takes O(klogn) time where k = len(lis).

        """
        intersection = []
        for i in lis:
            if self.in_interval(i):
                intersection.append(i)
        return intersection

    def union(self, interval):
        """Return the union of this interval with the given interval.

        Takes O(nlogn) time where n is the sum of the lengths of both intervals.
        We just build a new interval.

        """
        return Interval(intervals = self.intervals + interval.intervals)

    def difference(self, interval):
        """Return the set-theoretic difference of this interval with the given interval."""
        raise NotImplemented

    def __contains__(self, i):
        """Invoke in_interval."""
        return self.in_interval(i)

    def __eq__(self, other):
        """Return true if two intervals are precisely the same."""
        if not isinstance(other, Interval):
            return NotImplemented
        return all(map(lambda x: x[0] == x[1], zip(self.intervals, other.intervals)))
    
    def __ne__(self, other):
        """Return the negation of what __eq__ returns."""
        return not self.__eq__(other)
