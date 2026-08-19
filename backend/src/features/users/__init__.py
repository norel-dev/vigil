"""Users: the only actor the platform has.

There is no sign in and no self registration. A user exists because a
platform administrator created one, and calls the API with a key issued
against that record.

The router here also carries the endpoints for a caller's own API keys, which
is why it reaches into `src.identity`: a key belongs to a user, and asking
for one is something a user does about themselves.
"""
