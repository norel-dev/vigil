"""Tables: structured data a project holds inside a datastore.

The four modules are the whole feature. `model` is the platform's record of a
table — deliberately thin, because the shape of the data is the engine's to
know. `storage` is what a datastore must offer to be able to hold one, and
the privilege levels a statement may run at. `service` provisions and
resolves them. `router` puts them under their project in the URL.

The privilege boundary is the thing to understand here: the platform never
reads the SQL it is handed. It connects at the privilege the caller's role
earned and lets the engine refuse the rest, which is why creating and
dropping are methods on `TableStorage` rather than statements a caller could
send.
"""
