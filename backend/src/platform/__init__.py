"""The plumbing every feature stands on, and no feature owns.

Configuration, the errors the platform raises and how they reach the wire,
the components that outlive a request, and the dependencies that hand those
components to a request handler. Nothing here knows what a project or a blob
is, and nothing here should learn: a module that needs a feature belongs in
that feature.
"""
