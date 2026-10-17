"""Shared fixtures for the API tests.

Three things are real here that a faster suite would fake. The tests run
against a real Open Policy Agent server whenever the `opa` binary is
available, because a policy that is only exercised through a stub proves very
little about what the platform will actually allow. They reach a real MinIO
server whenever one can be started, because a signed URL is only worth
anything if the store it was signed for honours it - and a fake would honour
whatever the platform handed it, which is precisely the question. And they
authenticate with real API keys, verified by the real code, because since the
platform issues its own credentials there is no external service left to stand
in for.

What is arranged rather than earned is the users themselves: they are written
straight into the database, with a key whose text is derived from the caller's
name. That is what lets a test say `headers_for(caller="alice")` and get a
credential the application accepts on its own terms.
"""

import os
import shutil
import socket
import subprocess
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, select

from src.app import create_app
from src.database.engine import create_database_engine
from src.database.migrations import upgrade_to_head
from src.features.users.model import User
from src.identity.keys import digest_of
from src.identity.model import ApiKey
from src.platform.config import AppConfig, AuthConfig, DatabaseConfig, OpaConfig

#: The directory holding the Rego policy under test.
POLICY_DIRECTORY = Path(__file__).resolve().parent.parent / "policies"

#: The MinIO the tests run against when they fall back to Docker. Pinned to a
#: digestless tag on purpose: what is being tested is that the platform speaks
#: S3 correctly, so tracking the current server is the point.
MINIO_IMAGE = "quay.io/minio/minio:latest"

#: The PostgreSQL the metadata database runs on when the tests start their own.
POSTGRES_IMAGE = "postgres:18"

#: The environment variable naming a PostgreSQL server to use instead of
#: starting one. It is a SQLAlchemy URL whose user may create databases:
#:
#:   TEST_DATABASE_URL=postgresql+psycopg://postgres:password@localhost:5432/postgres
TEST_DATABASE_VARIABLE = "TEST_DATABASE_URL"

#: The callers every test can authenticate as, and the names they go by.
CALLERS = {
    "alice": "Alice",
    "bob": "Bob",
    "root": "Root",
}


def api_key_for(*, caller: str) -> str:
    """Return the API key the fixtures issue to `caller`.

    The key is derived from the caller's name rather than generated, so that a
    test can name a caller and get their credential without carrying one
    around. Nothing in the application knows or cares how a key was chosen: it
    recognises the digest, and the digest of this is what the fixture stored.

    Args:
        caller: The name of the caller.

    Returns:
        str: The key that authenticates them.
    """
    return f"dpk_test_key_for_{caller}_{'0' * 32}"


def _free_port() -> int:
    """Return a port that is free at the moment of asking.

    Returns:
        int: A currently unused TCP port on the loopback interface.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture(scope="session")
def opa_url() -> Iterator[str]:
    """Run an Open Policy Agent server holding the platform policy.

    Yields:
        str: The base URL of the running server.
    """
    binary = shutil.which("opa")
    if binary is None:
        pytest.skip("the 'opa' binary is not installed; see the README")

    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    server = subprocess.Popen(  # noqa: S603 - the binary is resolved from PATH
        [binary, "run", "--server", "--addr", f"127.0.0.1:{port}", str(POLICY_DIRECTORY)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    deadline = time.monotonic() + 30.0
    try:
        while time.monotonic() < deadline:
            if server.poll() is not None:
                pytest.fail("the OPA server exited before it became ready")
            try:
                if httpx.get(f"{url}/health", timeout=0.5).status_code == httpx.codes.OK:
                    break
            except httpx.HTTPError:
                time.sleep(0.1)
        else:
            pytest.fail("the OPA server did not become ready in time")

        yield url
    finally:
        server.terminate()
        server.wait(timeout=10)


@dataclass(frozen=True)
class MinIOServer:
    """Where a running MinIO is, and what gets in to it."""

    endpoint: str
    access_key: str
    secret_key: str


def _wait_until_ready(
    *, url: str, deadline: float, still_alive: Callable[[], bool]
) -> None:
    """Block until MinIO answers its health probe, or fail the test.

    Args:
        url: Base URL of the server being waited on.
        deadline: Monotonic time to give up at.
        still_alive: Returns False if the server has died, so that one which
            exits immediately is reported as that rather than as a timeout.

    Raises:
        pytest.fail.Exception: If the server never became ready.
    """
    while time.monotonic() < deadline:
        if not still_alive():
            pytest.fail("the MinIO server exited before it became ready")
        try:
            probe = httpx.get(f"{url}/minio/health/live", timeout=0.5)
            if probe.status_code == httpx.codes.OK:
                return
        except httpx.HTTPError:
            pass

        time.sleep(0.2)

    pytest.fail("the MinIO server did not become ready in time")


@contextmanager
def _running_minio() -> Iterator[MinIOServer]:
    """Run one MinIO server for as long as the block using it needs it.

    A local `minio` binary is preferred because it starts fastest; Docker is
    the fallback, since that is how most machines have MinIO available. When
    neither is there the blob tests skip, exactly as they do without `opa`.

    This is a context manager rather than a fixture because the suite needs
    more than one server: proving that a blob went to the datastore the caller
    chose takes a second store that the blob is provably *not* in, which one
    server shared by two datastores could never show.

    Yields:
        MinIOServer: Where the server is and how to authenticate to it.
    """
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    server = MinIOServer(
        endpoint=f"127.0.0.1:{port}",
        access_key="dataplatform-test",
        secret_key="dataplatform-test-secret",
    )
    environment = {
        "MINIO_ROOT_USER": server.access_key,
        "MINIO_ROOT_PASSWORD": server.secret_key,
    }

    if (binary := shutil.which("minio")) is not None:
        data = Path(tempfile.mkdtemp(prefix="minio-test-"))
        process = subprocess.Popen(  # noqa: S603 - the binary is resolved from PATH
            [binary, "server", "--address", f"127.0.0.1:{port}", str(data)],
            env={**os.environ, **environment},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            _wait_until_ready(
                url=url,
                deadline=time.monotonic() + 30.0,
                still_alive=lambda: process.poll() is None,
            )
            yield server
        finally:
            process.terminate()
            process.wait(timeout=10)
            shutil.rmtree(data, ignore_errors=True)

        return

    if shutil.which("docker") is None:
        pytest.skip("neither the 'minio' binary nor docker is available; see the README")

    started = subprocess.run(  # noqa: S603 - the binary is resolved from PATH
        [
            "docker", "run", "--detach", "--rm",
            "--publish", f"127.0.0.1:{port}:9000",
            "--env", f"MINIO_ROOT_USER={environment['MINIO_ROOT_USER']}",
            "--env", f"MINIO_ROOT_PASSWORD={environment['MINIO_ROOT_PASSWORD']}",
            MINIO_IMAGE, "server", "/data",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if started.returncode != 0:
        pytest.skip(f"a MinIO container could not be started: {started.stderr.strip()}")

    container = started.stdout.strip()

    def _container_running() -> bool:
        """Report whether the container is still up.

        Returns:
            bool: True while the container is running.
        """
        probe = subprocess.run(  # noqa: S603 - the binary is resolved from PATH
            ["docker", "inspect", "--format", "{{.State.Running}}", container],
            capture_output=True,
            text=True,
            check=False,
        )
        return probe.stdout.strip() == "true"

    try:
        _wait_until_ready(
            url=url, deadline=time.monotonic() + 60.0, still_alive=_container_running
        )
        yield server
    finally:
        subprocess.run(  # noqa: S603 - the binary is resolved from PATH
            ["docker", "kill", container],
            capture_output=True,
            check=False,
        )


@pytest.fixture(scope="session")
def minio_server() -> Iterator[MinIOServer]:
    """Run the MinIO server the blob tests sign URLs against.

    Yields:
        MinIOServer: Where the server is and how to authenticate to it.
    """
    with _running_minio() as server:
        yield server


@pytest.fixture(scope="session")
def other_minio_server() -> Iterator[MinIOServer]:
    """Run a second, unrelated MinIO server, on its own storage.

    Two servers rather than two datastores over one server is what makes the
    choice of datastore visible: a blob written to the datastore in front of
    this server is not merely recorded elsewhere, it is physically absent from
    the other, and a test can go and look.

    Yields:
        MinIOServer: Where the server is and how to authenticate to it.
    """
    with _running_minio() as server:
        yield server


@pytest.fixture(scope="session")
def postgres_server() -> Iterator[Engine]:
    """Reach a PostgreSQL server the tests may create databases on.

    The server named by `TEST_DATABASE_VARIABLE` is used when there is one.
    Otherwise a container is started for the session, and the tests that need
    a metadata database skip when Docker cannot provide it, exactly as the blob
    tests do without MinIO.

    Yields:
        Engine: An autocommitting engine on the server's maintenance database,
            for creating and dropping the databases the tests run against.
    """
    if (named := os.environ.get(TEST_DATABASE_VARIABLE)) is not None:
        server = create_engine(named, isolation_level="AUTOCOMMIT")
        try:
            yield server
        finally:
            server.dispose()
        return

    if shutil.which("docker") is None:
        pytest.skip(f"docker is not available and {TEST_DATABASE_VARIABLE} is not set")

    port = _free_port()
    started = subprocess.run(  # noqa: S603 - the binary is resolved from PATH
        [
            "docker", "run", "--detach", "--rm",
            "--publish", f"127.0.0.1:{port}:5432",
            "--env", "POSTGRES_PASSWORD=dataplatform-test",
            POSTGRES_IMAGE,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if started.returncode != 0:
        pytest.skip(f"a PostgreSQL container could not be started: {started.stderr.strip()}")

    container = started.stdout.strip()
    server = create_engine(
        f"postgresql+psycopg://postgres:dataplatform-test@127.0.0.1:{port}/postgres",
        isolation_level="AUTOCOMMIT",
    )
    try:
        deadline = time.monotonic() + 60.0
        while True:
            try:
                with server.connect():
                    break
            except OperationalError:
                if time.monotonic() > deadline:
                    pytest.fail("the PostgreSQL server did not become ready in time")
                time.sleep(0.2)

        yield server
    finally:
        server.dispose()
        subprocess.run(  # noqa: S603 - the binary is resolved from PATH
            ["docker", "kill", container],
            capture_output=True,
            check=False,
        )


@pytest.fixture
def database_url(postgres_server: Engine) -> Iterator[str]:
    """Provide an empty metadata database for one test, and throw it away after.

    Args:
        postgres_server: The server to create the database on.

    Yields:
        str: The SQLAlchemy URL of the empty database.
    """
    name = f"test_{uuid4().hex}"
    with postgres_server.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))

    yield postgres_server.url.set(database=name).render_as_string(hide_password=False)

    with postgres_server.connect() as connection:
        # Forced, so that a test which leaked a connection still cleans up.
        connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))


@pytest.fixture
def config(database_url: str, opa_url: str) -> AppConfig:
    """Build a configuration pointing at a throwaway database and the test OPA.

    No bootstrap administrator is configured: the tests create the users they
    need themselves, and promote one when they want an administrator, so that
    every test starts from a platform where nobody is trusted.

    Args:
        database_url: URL of the test's own empty metadata database.
        opa_url: Base URL of the policy server.

    Returns:
        AppConfig: Configuration for a single test.
    """
    return AppConfig(
        database=DatabaseConfig(url=database_url, echo=False),
        auth=AuthConfig(),
        opa=OpaConfig(url=opa_url),
    )


@pytest.fixture
def engine(config: AppConfig) -> Iterator[Engine]:
    """Create the test database and migrate it to the latest revision.

    The schema every test runs against is built by the migrations rather than
    from the models, so the suite is also a check that the two agree.

    Args:
        config: Configuration for the running test.

    Yields:
        Engine: An engine bound to the throwaway database.
    """
    engine = create_database_engine(config=config.database)
    upgrade_to_head(engine=engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    """Open a session tests can use to arrange data directly.

    Args:
        engine: The engine of the throwaway database.

    Yields:
        Session: A session that is closed when the test ends.
    """
    with Session(engine) as session:
        yield session


@pytest.fixture
def callers(engine: Engine) -> dict[str, UUID]:
    """Register the callers the tests authenticate as, each with a key.

    Args:
        engine: The engine of the throwaway database.

    Returns:
        dict[str, UUID]: Caller name to the id the platform gave them.
    """
    registered: dict[str, UUID] = {}
    with Session(engine) as session:
        for caller, name in CALLERS.items():
            user = User(email=f"{caller}@example.com", name=name)
            session.add(user)
            session.add(
                ApiKey(
                    user_id=user.id,
                    name="test",
                    secret_hash=digest_of(key=api_key_for(caller=caller)),
                )
            )
            registered[caller] = user.id
        session.commit()

    return registered


@pytest.fixture
def client(
    config: AppConfig,
    engine: Engine,
    callers: dict[str, UUID],
) -> Iterator[TestClient]:
    """Build the application the tests call, with nothing about it stubbed.

    The database, the routers, the authentication and the decisions all come
    from the real application, so what the tests exercise is the wiring that
    will run in production.

    Args:
        config: Configuration for the running test.
        engine: The engine of the throwaway database, created before the app
            so that the schema exists when the first request arrives.
        callers: The users the tests authenticate as.

    Yields:
        TestClient: A client whose keys are the ones `headers_for` produces.
    """
    app: FastAPI = create_app(config=config)

    with TestClient(app) as client:
        yield client


def headers_for(*, caller: str) -> dict[str, str]:
    """Return the request headers that authenticate `caller`.

    Args:
        caller: The name of the caller.

    Returns:
        dict[str, str]: Headers carrying the caller's API key.
    """
    return {"Authorization": f"Bearer {api_key_for(caller=caller)}"}


def user_id_of(*, client: TestClient, caller: str) -> UUID:
    """Return the id the platform gave `caller`, by asking it as them.

    Args:
        client: The test client.
        caller: The name of the caller.

    Returns:
        UUID: The id the platform assigned to that caller.
    """
    response = client.get("/users/me", headers=headers_for(caller=caller))
    assert response.status_code == httpx.codes.OK, response.text
    return UUID(response.json()["id"])


def make_platform_admin(*, session: Session, email: str) -> User:
    """Promote the user with address `email` to platform administrator.

    Args:
        session: An open session on the test database.
        email: Address of the user to promote.

    Returns:
        User: The promoted user.
    """
    user = session.exec(select(User).where(User.email == email)).one()
    user.is_platform_admin = True
    session.add(user)
    session.commit()
    session.refresh(user)
    return user
