"""Resolve a patient's graph diagnoses to curated scraper topics.

The document pipeline writes medical entities to Neo4j through Graphiti with
``group_id = uid``. This module reads Diagnosis nodes for that UID, maps their
name/ICD properties onto the curated disease tags in ``topics.py``, and returns
the matching PubMed topic definitions.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from neo4j import GraphDatabase

from .topics import DISEASE_TOPICS, diseases_for_diagnosis, disease_for_text

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PatientDiagnosis:
    """Diagnosis-like entity read from the patient's Graphiti/Neo4j namespace."""

    name: str | None
    icd_code: str | None
    properties: dict[str, Any]


@dataclass(frozen=True)
class PatientTopicResolution:
    """Resolved diseases and the source diagnoses that produced them."""

    uid: str
    diagnoses: list[PatientDiagnosis]
    disease_tags: list[str]
    topics: list[dict]


def resolve_topics_for_uid(uid: str, *, limit: int = 200) -> PatientTopicResolution:
    """Read a user's graph diagnoses and map them to curated scraper topics."""
    diagnoses = fetch_patient_diagnoses(uid, limit=limit)
    disease_tags = sorted(
        {
            tag
            for diagnosis in diagnoses
            if (tag := _disease_for_graph_diagnosis(diagnosis)) is not None
        }
    )
    topics_by_tag = {topic["disease"]: topic for topic in DISEASE_TOPICS}
    topics = [topics_by_tag[tag] for tag in disease_tags if tag in topics_by_tag]

    _log.info(
        "patient_topics_resolved uid=%s diagnoses=%d diseases=%s",
        uid,
        len(diagnoses),
        ",".join(disease_tags),
    )
    return PatientTopicResolution(
        uid=uid,
        diagnoses=diagnoses,
        disease_tags=disease_tags,
        topics=topics,
    )


def fetch_patient_diagnoses(uid: str, *, limit: int = 200) -> list[PatientDiagnosis]:
    """Return Diagnosis nodes from the Graphiti graph namespace for ``uid``.

    Graphiti stores custom entity classes as Neo4j labels, so the primary query
    looks for nodes labelled ``Diagnosis`` under this user's ``group_id``. A
    small fallback also checks the serialized/entity-type properties in case a
    future Graphiti version changes the concrete labels.
    """
    with _neo4j_driver() as driver:
        database = os.environ.get("NEO4J_DATABASE", "neo4j")
        with driver.session(database=database) as session:
            rows = session.run(
                """
                MATCH (d)
                WHERE d.group_id = $uid
                  AND (
                    "Diagnosis" IN labels(d)
                    OR toLower(coalesce(properties(d).entity_type, "")) = "diagnosis"
                    OR toLower(coalesce(properties(d).type, "")) = "diagnosis"
                  )
                RETURN DISTINCT properties(d) AS props
                LIMIT $limit
                """,
                uid=uid,
                limit=limit,
            )
            return [_diagnosis_from_props(dict(row["props"])) for row in rows]


def _neo4j_driver():
    return GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
    )


def _diagnosis_from_props(props: dict[str, Any]) -> PatientDiagnosis:
    return PatientDiagnosis(
        name=_first_text(props, "name", "label", "summary", "description"),
        icd_code=_first_text(props, "icd_code", "icd", "code"),
        properties=props,
    )


def _disease_for_graph_diagnosis(diagnosis: PatientDiagnosis) -> str | None:
    # Prefer explicit fields first.
    tag = diseases_for_diagnosis(diagnosis.name, diagnosis.icd_code)
    if tag:
        return tag

    # Be forgiving with Graphiti property shapes: aliases can be hidden in a
    # summary or other extracted property even when ``name`` is too generic.
    searchable = " ".join(
        str(value)
        for value in diagnosis.properties.values()
        if isinstance(value, (str, int, float))
    )
    return disease_for_text(searchable)


def _first_text(props: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = props.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None
