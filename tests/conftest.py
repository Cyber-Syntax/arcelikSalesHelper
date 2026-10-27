import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # before any Qt import

import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from arcelikSalesHelper.domain.result import Ok
from arcelikSalesHelper.infrastructure.database import open_database
from arcelikSalesHelper.infrastructure.repositories import ProductRepository


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: int = 60) -> None:
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def db(tmp_path) -> Iterator[sqlite3.Connection]:  # type: ignore[no-untyped-def]
    result = open_database(tmp_path / "test.sqlite")
    assert isinstance(result, Ok), result
    conn = result.value
    yield conn
    conn.close()


@pytest.fixture
def repo(db: sqlite3.Connection, clock: FakeClock) -> ProductRepository:
    return ProductRepository(db, clock)
