"""Tests of what may be used as the name of a blob.

A key is the whole of a blob's name and the only hierarchy blobs have:
`reports/2026/q1.parquet` is one key, not a folder holding a file. The rule
matters more than that phrasing suggests, because the key is interpolated into
a URL that is then signed - so a key that does not mean one fixed place is a
key that could be made to mean somebody else's.

These run against the rule itself rather than through a store, so they need
neither MinIO nor Docker. `tests/test_blob_storage.py` checks that the
implementation applies the rule before it reaches the network, and
`tests/test_blob_access.py` checks that the API answers a bad key with a 4xx.
"""

import pytest

from src.features.blobs.storage import validate_object_key

#: The longest key the platform accepts, from S3's own limit.
MAX_KEY_LENGTH = 1024

#: The longest one segment between slashes may be.
MAX_SEGMENT_LENGTH = 255


def _key_of_length(*, total: int, segments: int) -> str:
    """Build a valid-shaped key of exactly `total` characters.

    Length is capped twice over - once for the whole key and once for each
    segment - so a long key has to be spread across several segments to be
    testing the limit it means to test.

    Args:
        total: The length the finished key should have.
        segments: How many pieces to spread it across.

    Returns:
        str: A key of exactly `total` characters.

    Raises:
        ValueError: If the length cannot be built from that many segments.
    """
    length, remainder = divmod(total - (segments - 1), segments)
    if remainder or not 0 < length <= MAX_SEGMENT_LENGTH:
        raise ValueError(f"{total} characters do not divide into {segments} segments")

    return "/".join(["a" * length] * segments)


@pytest.mark.parametrize(
    "key",
    [
        pytest.param("report.parquet", id="a plain name"),
        pytest.param("reports/2026/q1.parquet", id="a path shaped name"),
        pytest.param("a", id="a single character"),
        pytest.param("2026-01-01_snapshot.tar.gz", id="dots and dashes"),
        pytest.param("model_v2.final", id="an underscore"),
        pytest.param("0", id="starting with a digit"),
        pytest.param(
            _key_of_length(total=MAX_KEY_LENGTH, segments=5),
            id="exactly at the length limit",
        ),
        pytest.param("a" * MAX_SEGMENT_LENGTH, id="a segment at its own limit"),
        pytest.param("/".join(["dir"] * 50) + "/f.txt", id="deeply nested"),
    ],
)
def test_the_names_people_actually_use_are_accepted(key: str) -> None:
    """The rule has to leave ordinary object names alone to be worth having."""
    assert validate_object_key(key=key) == key


@pytest.mark.parametrize(
    "key",
    [
        pytest.param("", id="empty"),
        pytest.param("/leading.txt", id="a leading slash"),
        pytest.param("trailing/", id="a trailing slash"),
        pytest.param("two//slashes.txt", id="an empty segment"),
        pytest.param(".", id="the current directory"),
        pytest.param("..", id="the parent directory"),
        pytest.param("../escape.txt", id="climbing out"),
        pytest.param("reports/../../etc/passwd", id="climbing out from inside"),
        pytest.param("reports/./q1.parquet", id="a no-op segment"),
    ],
)
def test_a_key_that_does_not_mean_one_fixed_place_is_refused(key: str) -> None:
    """These are the shapes that stop a key naming exactly one blob.

    Every one of them resolves to somewhere other than where it reads, once it
    is joined onto a bucket and handed to something that resolves URLs.
    """
    with pytest.raises(ValueError):
        validate_object_key(key=key)


@pytest.mark.parametrize(
    "key",
    [
        pytest.param("-leading-dash.txt", id="starting with a dash"),
        pytest.param(".hidden", id="starting with a dot"),
        pytest.param("_private", id="starting with an underscore"),
        pytest.param("with space.txt", id="a space"),
        pytest.param("question?.txt", id="a query string marker"),
        pytest.param("hash#fragment", id="a fragment marker"),
        pytest.param("semi;colon", id="a semicolon"),
        pytest.param("back\\slash", id="a backslash"),
        pytest.param("percent%2F.txt", id="an encoded slash"),
        pytest.param("new\nline", id="a newline"),
        pytest.param("null\0byte", id="a null byte"),
        pytest.param("naïve.txt", id="a non-ascii letter"),
    ],
)
def test_a_key_holding_anything_but_the_allowed_characters_is_refused(
    key: str,
) -> None:
    """The set is small on purpose: everything else is one less thing to reason about.

    Several of these would survive a round trip perfectly well. They are
    refused anyway, because the question a signed URL raises is not whether a
    character works but whether it can be made to mean two things.
    """
    with pytest.raises(ValueError):
        validate_object_key(key=key)


def test_a_key_longer_than_the_store_allows_is_refused() -> None:
    """Refused here, rather than by MinIO after the platform has recorded it.

    Every segment of this one is short enough on its own, so what turns it
    down is the limit on the whole key rather than the limit on a piece.
    """
    too_long = _key_of_length(total=MAX_KEY_LENGTH + 5, segments=5)

    with pytest.raises(ValueError, match=f"at most {MAX_KEY_LENGTH} characters"):
        validate_object_key(key=too_long)


def test_a_single_segment_longer_than_the_store_allows_is_refused() -> None:
    """A key may be long; one piece of it between slashes may not."""
    with pytest.raises(ValueError, match="at most 255 characters"):
        validate_object_key(key="a" * (MAX_SEGMENT_LENGTH + 1) + "/f.txt")


def test_an_empty_key_says_so_rather_than_complaining_about_its_shape() -> None:
    """The commonest mistake gets the message that names it."""
    with pytest.raises(ValueError, match="cannot be empty"):
        validate_object_key(key="")
