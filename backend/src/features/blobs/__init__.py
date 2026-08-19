"""Blobs: unstructured data a project holds inside a datastore.

The same four modules as `src.features.tables`, drawing the same boundary by
a different mechanism. There is no statement for an engine to refuse, so the
platform signs a URL good for one method on one key and lets the object store
turn away everything else. The bytes never pass through the API.

Blobs have no hierarchy. A key may read like a path, but there is no folder
in it and nothing to create before using it, which is why a project holds
blobs directly rather than holding containers that hold blobs.
"""
