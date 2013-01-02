"""A simple multidict using Python's built-in defaultdict class in combination with lists."""

import collections.defaultdict

def multidict():
    """Return a new empty multidict."""
    return collections.defaultdict(list)
