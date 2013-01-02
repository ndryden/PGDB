"""A simple interface for invoking callbacks based on records."""

from gdbmi_identifier import GDBMIRecordIdentifier

class GDBMIRecordHandler:
    """Invoke callbacks based on record identifications.

    This supports callbacks based either on the token in the record, or matching a provided
    identification.

    """

    def __init__(self, identifier):
        """Initialize the record handler."""
        self.identifier = identifier
        self.token_handlers = {}
        self.ident_handlers = []

    def add_handler(self, func, token = None, ident = None, data = None):
        """Add a handler.

        func is the function to invoke.
        token, if present, invokes this handler on a record with this token.
        ident, if present, invokes this handler on a record that has all the identifications in this.
        data is passed to the function in the keyword argument "data".

        Returns a token ID and an identifier ID (either of which may be None).

        """
        tret = None
        iret = None
        if token:
            token = int(token)
            self.token_handlers[token] = (func, data)
            tret = token
        if ident:
            self.ident_handlers.append((ident, func, data))
            iret = len(self.ident_handlers) - 1
        return tret, iret

    def remove_handler(self, tid = None, iid = None):
        """Remove a handler.

        tid is the token callback ID.
        iid is the identifier ID.

        """
        if tid:
            del self.token_handlers[tid]
        if iid:
            del self.ident_handlers[iid]

    def handle(self, record, **kwargs):
        """Handle a record, passing any keyword arguments to the handlers."""
        ret = True
        if record.token in self.token_handlers:
            tup = self.token_handlers[record.token]
            kwargs["data"] = tup[1]
            ret = ret and tup[0](record, tid = record.token, **kwargs)
        ident = self.identifier.identify(record)
        for k, tup in enumerate(self.ident_handlers):
            test = tup[0]
            def _in(x):
                return x in ident
            if all(map(_in, test)):
                kwargs["data"] = tup[2]
                ret = ret and tup[1](record, iid = k, **kwargs)
        return ret
