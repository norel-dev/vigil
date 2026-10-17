"""Tests of reading the configuration file the process is started with.

This is the one thing the platform does before it has a database, a policy
engine or a caller, so a mistake here is a mistake nothing downstream can
report properly. The tests are therefore mostly about the ways a file can be
wrong, and they check that each one is refused as a `ConfigurationError`
naming the file - rather than surfacing later as a missing key, a `None` where
a URL was expected, or a process that starts and then cannot do anything.

`tests/test_bootstrap_admin.py` covers what the administrators section is
allowed to say. What is covered here is the file around it.
"""

from pathlib import Path

import pytest

from src.platform.config import AppConfig, load_config
from src.platform.environment import (
    CONFIG_PATH_VARIABLE,
    DEFAULT_CONFIG_PATH,
    configuration_path,
    load_configuration,
)
from src.platform.exceptions import ConfigurationError

#: The smallest file the platform will start from. Only the database section
#: has no usable default, so everything else here is left out on purpose to
#: check that it really is optional.
MINIMAL_CONFIG = """
database:
  url: postgresql+psycopg://dataplatform:secret@localhost:5432/minimal
auth: {}
opa: {}
"""


def _write(*, path: Path, text: str) -> Path:
    """Write `text` to `path` and return the path.

    Args:
        path: Where to write the file.
        text: The contents to write.

    Returns:
        Path: The path that was written to.
    """
    path.write_text(text, encoding="utf-8")
    return path


# --- a file that is right ---------------------------------------------------


def test_the_smallest_usable_file_loads(tmp_path: Path) -> None:
    """Everything but the database has a default, so this is enough to start."""
    config = load_config(path=_write(path=tmp_path / "c.yaml", text=MINIMAL_CONFIG))

    assert isinstance(config, AppConfig)
    assert config.database.url == "postgresql+psycopg://dataplatform:secret@localhost:5432/minimal"
    assert config.auth.bootstrap_platform_admins == []


def test_the_defaults_are_the_ones_the_file_did_not_have_to_state(
    tmp_path: Path,
) -> None:
    """A file that omits OPA still points at something, rather than at nothing."""
    config = load_config(path=_write(path=tmp_path / "c.yaml", text=MINIMAL_CONFIG))

    assert config.opa.url.startswith("http")
    assert config.opa.decision_path
    assert config.opa.filter_path
    assert config.opa.request_timeout_seconds > 0
    assert config.database.echo is False


def test_what_the_file_states_wins_over_the_default(tmp_path: Path) -> None:
    """Otherwise a deployment could not point the platform at its own OPA."""
    text = """
database:
  url: postgresql+psycopg://dataplatform:secret@localhost:5432/stated
  echo: true
auth: {}
opa:
  url: http://opa.internal:8181
  request_timeout_seconds: 0.5
"""

    config = load_config(path=_write(path=tmp_path / "c.yaml", text=text))

    assert config.database.echo is True
    assert config.opa.url == "http://opa.internal:8181"
    assert config.opa.request_timeout_seconds == 0.5


def test_the_example_file_in_the_repository_still_describes_this_schema(
    tmp_path: Path,
) -> None:
    """The file a deployment copies has to keep matching the settings it names.

    Only the placeholder key is replaced, because that is the one thing the
    example deliberately does not supply. Everything else is loaded as
    written, so a section renamed in the code and not in the example is a
    failure here rather than a surprise for whoever copies it.
    """
    example = Path(__file__).resolve().parent.parent / "config.example.yaml"
    filled = example.read_text(encoding="utf-8").replace(
        "REPLACE_ME", "dpk_" + "a" * 40
    )

    config = load_config(path=_write(path=tmp_path / "copied.yaml", text=filled))

    assert config.database.url
    assert len(config.auth.bootstrap_platform_admins) == 1
    assert config.opa.url


def test_the_example_file_cannot_be_started_from_unedited() -> None:
    """Its placeholder key is refused, so nobody deploys with a known secret."""
    example = Path(__file__).resolve().parent.parent / "config.example.yaml"

    with pytest.raises(ConfigurationError, match="at least"):
        load_config(path=example)


# --- a file that is wrong ---------------------------------------------------


def test_a_missing_file_is_reported_as_a_configuration_error(tmp_path: Path) -> None:
    """Naming a file that is not there is the commonest way to get this wrong."""
    missing = tmp_path / "not-here.yaml"

    with pytest.raises(ConfigurationError, match="Could not read config file"):
        load_config(path=missing)


def test_a_directory_is_reported_the_same_way_as_a_missing_file(
    tmp_path: Path,
) -> None:
    """Pointing at the config *directory* is refused rather than crashed on."""
    with pytest.raises(ConfigurationError, match="Could not read config file"):
        load_config(path=tmp_path)


def test_a_file_that_is_not_yaml_is_refused(tmp_path: Path) -> None:
    """The parser's complaint is carried through, since it locates the mistake."""
    broken = _write(path=tmp_path / "c.yaml", text="database: [unclosed\n")

    with pytest.raises(ConfigurationError, match="is not valid YAML"):
        load_config(path=broken)


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("- database\n- auth\n", id="a list"),
        pytest.param("just a string\n", id="a string"),
        pytest.param("", id="an empty file"),
    ],
)
def test_a_file_that_is_not_a_mapping_is_refused(tmp_path: Path, text: str) -> None:
    """Valid YAML that is not a settings document would validate to nothing."""
    with pytest.raises(ConfigurationError, match="must contain a YAML mapping"):
        load_config(path=_write(path=tmp_path / "c.yaml", text=text))


def test_a_file_missing_a_section_the_platform_needs_is_refused(
    tmp_path: Path,
) -> None:
    """There is no sensible default for where the metadata lives."""
    text = "auth: {}\nopa: {}\n"

    with pytest.raises(ConfigurationError, match="is invalid"):
        load_config(path=_write(path=tmp_path / "c.yaml", text=text))


@pytest.mark.parametrize(
    "url",
    [
        "sqlite:///metadata.db",
        "postgresql://dataplatform:secret@localhost:5432/dataplatform",
        "not a url at all",
    ],
)
def test_a_metadata_database_that_is_not_postgresql_through_psycopg_is_refused(
    tmp_path: Path, url: str
) -> None:
    """The migrations are written for PostgreSQL alone, so nothing else may start.

    A bare `postgresql://` is refused too: SQLAlchemy would reach for psycopg2,
    which the platform does not install, and fail at the first connection
    rather than here.

    Args:
        tmp_path: Directory unique to the running test.
        url: A URL the platform must not accept.
    """
    text = f"database:\n  url: {url}\nauth: {{}}\nopa: {{}}\n"

    with pytest.raises(ConfigurationError, match="is invalid"):
        load_config(path=_write(path=tmp_path / "c.yaml", text=text))


def test_a_value_of_the_wrong_shape_is_refused(tmp_path: Path) -> None:
    """A timeout of 'soon' would otherwise fail at the first decision instead."""
    text = """
database:
  url: postgresql+psycopg://dataplatform:secret@localhost:5432/wrong
auth: {}
opa:
  request_timeout_seconds: soon
"""

    with pytest.raises(ConfigurationError, match="is invalid"):
        load_config(path=_write(path=tmp_path / "c.yaml", text=text))


def test_the_failure_names_the_file_it_was_reading(tmp_path: Path) -> None:
    """A deployment usually has more than one, so which one matters."""
    broken = _write(path=tmp_path / "the-one-in-use.yaml", text="[]\n")

    with pytest.raises(ConfigurationError, match="the-one-in-use.yaml"):
        load_config(path=broken)


# --- which file that is -----------------------------------------------------


def test_the_default_file_is_used_when_the_environment_says_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Running the platform from a checkout needs no environment at all."""
    monkeypatch.delenv(CONFIG_PATH_VARIABLE, raising=False)

    assert configuration_path() == DEFAULT_CONFIG_PATH


def test_the_environment_chooses_the_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """This is how a deployment points the process at its own settings."""
    chosen = tmp_path / "deployed.yaml"
    monkeypatch.setenv(CONFIG_PATH_VARIABLE, str(chosen))

    assert configuration_path() == chosen


def test_the_process_loads_the_file_the_environment_chose(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The two halves together: the variable picks the file, and it is read.

    This is the whole of what an entry point does before it has anything else,
    so it is worth pinning down as one step rather than only as two.
    """
    chosen = _write(path=tmp_path / "deployed.yaml", text=MINIMAL_CONFIG)
    monkeypatch.setenv(CONFIG_PATH_VARIABLE, str(chosen))

    assert load_configuration().database.url == "postgresql+psycopg://dataplatform:secret@localhost:5432/minimal"


def test_a_bad_file_named_by_the_environment_still_fails_as_configuration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The entry point reports a configuration problem, not an OS error."""
    monkeypatch.setenv(CONFIG_PATH_VARIABLE, str(tmp_path / "absent.yaml"))

    with pytest.raises(ConfigurationError):
        load_configuration()
