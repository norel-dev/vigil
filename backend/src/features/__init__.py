"""One package per thing the platform offers.

Each package here holds a whole feature rather than one layer of several:
the record that is stored, the service that acts on it, the router that
exposes it, and — where the feature reaches storage outside the platform's
own database — the protocol that storage has to satisfy. Reading a feature
end to end means reading one directory.

The packages are deliberately shallow in what they know of each other. A
feature may call another feature's service (a table has to resolve its
datastore before it can be provisioned), but no `__init__` re-exports
anything, so an import always names the module it means and the graph stays
acyclic.

What is *not* here is anything a feature merely uses: configuration and
errors are in `src.platform`, the metadata database is in `src.database`,
who the caller is is in `src.identity`, and what they may do is in
`src.authz`.
"""
