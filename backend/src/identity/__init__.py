"""Who is calling.

A caller presents an API key this platform issued, and this package is what
turns that string into the user behind it: `keys` is what a key is made of,
`model` is the row that is kept of one, `service` issues and withdraws them,
and `caller` is the dependency a route asks for to learn who it is serving.
`bootstrap` is the way into a platform that has no users yet.

Authentication needs no seam behind an interface, unlike authorization. The
platform issues its own credentials and holds the digest of them, so there is
nothing external to stand an abstraction in front of.

What the caller may then *do* is `src.authz`, and the two are kept apart on
purpose: the pair of them differ by one letter when abbreviated, and the
mistake that name invites is exactly the mistake worth not making.
"""
