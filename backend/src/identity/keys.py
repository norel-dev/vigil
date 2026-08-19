"""What an API key is, and what the platform keeps of one.

A key is a long random string the platform generates once and hands over
once. From then on the platform holds nothing but a digest of it, so a caller
presenting a key is recognised by looking the digest up rather than by
comparing anything against a stored secret.

Two decisions are worth stating, because both look like corners cut and are
not:

* **The digest is a plain SHA-256, not a password hash.** Password hashes are
  slow on purpose, because a password is short and chosen by a person and
  therefore guessable. A key here is 256 bits from `secrets.token_urlsafe`,
  which no amount of guessing reaches, so the slowness would buy nothing and
  would be paid on every single request.
* **Lookup is by digest, and there is no secret comparison to time.** The
  digest of the presented key is what the database is asked for; a key that
  is not in the table simply matches no row. Nothing branches on a partial
  match, so there is no comparison for a timing attack to observe.

The `dpk_` prefix is cosmetic. It is there so a key found in a log or a
repository is recognisable as this platform's, and nothing verifies it: a key
is whatever string the digest was taken of.
"""

import hashlib
import secrets

__all__ = ["KEY_PREFIX", "digest_of", "generate_key"]

#: Marks a string as one of this platform's keys, for whoever finds one.
KEY_PREFIX = "dpk_"

#: Bytes of randomness behind a generated key. 32 is the point past which the
#: key stops being the weakest thing in the request.
_SECRET_BYTES = 32


def generate_key() -> str:
    """Return a new API key, which is the only time it will ever exist in full.

    Returns:
        str: The key to hand to its holder.
    """
    return f"{KEY_PREFIX}{secrets.token_urlsafe(_SECRET_BYTES)}"


def digest_of(*, key: str) -> str:
    """Return the digest the platform stores and recognises `key` by.

    Args:
        key: The key, as it was handed out or as a caller presented it.

    Returns:
        str: The SHA-256 digest of the key, in hex.
    """
    return hashlib.sha256(key.encode("utf-8")).hexdigest()
