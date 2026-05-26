"""
Singleton Neo4j driver.

Configure via environment variables:
  NEO4J_URI      bolt://localhost:7687         (local Docker)
                 neo4j+s://xxxx.databases.neo4j.io  (Aura remote)
  NEO4J_USER     neo4j
  NEO4J_PASSWORD your_password

The driver is created once on first use and reused across all requests.
Call close_driver() on application shutdown.
"""

from __future__ import annotations

import logging
import os

from neo4j import Driver, GraphDatabase, Session

_log = logging.getLogger(__name__)
_driver: Driver | None = None
_database: str = "neo4j"


def get_driver() -> Driver:
    global _driver, _database
    if _driver is None:
        uri = os.environ["NEO4J_URI"]
        _database = os.environ.get("NEO4J_DATABASE", "neo4j")
        _driver = GraphDatabase.driver(
            uri,
            auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
        )
        _log.info("neo4j_driver_created uri=%s database=%s", uri, _database)
    return _driver


def get_session() -> Session:
    """Open a session against the configured database."""
    return get_driver().session(database=_database)


def close_driver() -> None:
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None
        _log.info("neo4j_driver_closed")
