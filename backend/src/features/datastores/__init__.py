"""Datastores: the storage the whole platform is built on.

A datastore is part of the platform itself rather than of any project. It
describes hardware everybody shares, so it belongs to nobody and only
platform administrators manage one. Projects reach the data behind a
datastore through objects of their own — a table, a blob — and never through
the datastore.

`storage` is the vocabulary shared by everything that reaches a store.
`model` is the record, and the union of implementations the API accepts.
`implementations` holds one module per concrete store. What a store can
*hold* is not here: that is declared beside the feature that holds it, in
`src.features.tables.storage` and `src.features.blobs.storage`, so that a
store keeping blobs never has to stub out a method about tables.
"""
