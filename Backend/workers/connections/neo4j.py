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

from neo4j import Driver, GraphDatabase

_log = logging.getLogger(__name__)
_driver: Driver | None = None


def get_driver() -> Driver:
    global _driver
    if _driver is None:
        uri = os.environ["NEO4J_URI"]
        _driver = GraphDatabase.driver(
            uri,
            auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
        )
        _log.info("neo4j_driver_created uri=%s", uri)
    return _driver


def close_driver() -> None:
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None
        _log.info("neo4j_driver_closed")
