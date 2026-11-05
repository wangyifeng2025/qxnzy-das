"""测试使用独立库 qxnzy_das_test，不读写开发库。"""

import os
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/qxnzy_das_test",
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from app.api.deps import get_db_session  # noqa: E402
from app.db import async_session_factory, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seeds.initial_data import seed_all  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]


async def _ensure_database() -> None:
    admin_url, database = TEST_DATABASE_URL.rsplit("/", 1)
    admin_url = admin_url.removeprefix("postgresql+asyncpg://").removeprefix("postgresql://")
    connection = await asyncpg.connect(f"postgresql://{admin_url}/postgres")
    try:
        exists = await connection.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", database)
        if exists is None:
            await connection.execute(f'CREATE DATABASE "{database}"')
    finally:
        await connection.close()


def _migrate() -> None:
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=BACKEND,
        check=True,
        env={**os.environ, "DATABASE_URL": TEST_DATABASE_URL},
    )


@pytest.fixture(scope="session")
async def _database() -> None:
    await _ensure_database()
    _migrate()
    async with async_session_factory() as session:
        await seed_all(session)


@pytest.fixture
async def db_session(_database: None) -> AsyncIterator[AsyncSession]:
    connection = await engine.connect()
    transaction = await connection.begin()
    session = AsyncSession(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        await session.close()
        await transaction.rollback()
        await connection.close()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    async def override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db_session] = override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    app.dependency_overrides.clear()
