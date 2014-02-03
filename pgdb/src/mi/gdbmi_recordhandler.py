"""A simple interface for invoking callbacks based on records."""

class GDBMIRecordHandler:
    """Invoke callbacks based on record identifications.

    This supports callbacks based upon either the token or the record type and
    subtypes.

    """

    def __init__(self):
        """Initialize the record handler."""
        self.token_handlers = {}
        self.type_handlers = {}
        self.handler_id = 0

    def add_token_handler(self, func, token, data = None):
        """Add a token handler.

        func is the function to invoke.
        token is the token to invoke this handler on.
        data is passed to func in the keyword argument data.

        Returns a handler ID.

        """
        hid = self.handler_id
        self.handler_id += 1
        if token in self.token_handlers:
            self.token_handlers[token].append((hid, func, data))
        else:
            self.token_handlers[token] = [(hid, func, data)]
        return hid

    def add_type_handler(self, func, types, data = None):
        """Add a type handler.

        func is the function to invoke.
        types is a set and will invoke the handler on a record if types is a
        subset of the record's types.
        data is passed to func in the keyword argument data.

        Returns a handler ID.

        """
        frozen_types = frozenset(types)
        hid = self.handler_id
        self.handler_id += 1
        if frozen_types in self.type_handlers:
            self.type_handlers[frozen_types].append((hid, func, data))
        else:
            self.type_handlers[frozen_types] = [(hid, func, data)]
        return hid

    def remove_handler(self, hid):
        """Remove a handler.

        hid is the handler ID returned by add_{token,type}_handler.

        """
        key = None
        for k in self.token_handlers:
            if self.token_handlers[k][0] == hid:
                key = k
                break
        if key is not None:
            del self.token_handlers[k]
        for k in self.type_handlers:
            if self.type_handlers[k][0] == hid:
                key = k
                break
        if key is not None:
            del self.type_handlers[k]

    def handle(self, record, **kwargs):
        """Handle a record, passing any keyword arguments to the handlers."""
        ret = []
        if record.token in self.token_handlers:
            tup = self.token_handlers[record.token]
            kwargs["data"] = tup[2]
            ret.append(tup[1](record, **kwargs))
        types = record.record_subtypes.union([record.record_type])
        for k in self.type_handlers:
            if k.issubset(types):
                for handler in self.type_handlers[k]:
                    kwargs["data"] = handler[2]
                    ret.append(handler[1](record, **kwargs))
        return ret
