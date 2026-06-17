from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    base_dir: Path

    neo4j_uri: str | None
    neo4j_user: str | None
    neo4j_password: str | None
    neo4j_database: str | None
    neo4j_query_timeout_seconds: float

    llm_provider: str
    gemini_model: str
    gemini_temperature: float
    gemini_max_output_tokens: int
    gemini_api_key: str | None
    google_cloud_project: str | None
    google_cloud_location: str
    openai_api_key: str | None

    graphiti_search_enabled: bool
    graphiti_search_limit: int

    default_query_limit: int
    schema_pattern_limit: int
    max_rows_for_answer: int
    max_history_turns: int
    cors_allowed_origins: list[str]

    @property
    def neo4j_configured(self) -> bool:
        return bool(self.neo4j_uri and self.neo4j_user and self.neo4j_password)

    @property
    def llm_configured(self) -> bool:
        if self.llm_provider == "google-genai":
            return bool(self.gemini_api_key)
        if self.llm_provider == "vertex":
            # Vertex can sometimes infer project from ADC, so do not require it here.
            return True
        return False

    @property
    def graphiti_search_configured(self) -> bool:
        return bool(
            self.graphiti_search_enabled
            and self.neo4j_configured
            and self.openai_api_key
        )


def load_config(base_dir: Path) -> AppConfig:
    _load_env_files(base_dir)

    llm_provider = os.environ.get("LLM_PROVIDER")
    if not llm_provider:
        llm_provider = "google-genai" if os.environ.get("GEMINI_API_KEY") else "vertex"

    return AppConfig(
        base_dir=base_dir,
        neo4j_uri=os.environ.get("NEO4J_URI"),
        neo4j_user=os.environ.get("NEO4J_USER") or os.environ.get("NEO4J_USERNAME"),
        neo4j_password=os.environ.get("NEO4J_PASSWORD"),
        neo4j_database=os.environ.get("NEO4J_DATABASE") or None,
        neo4j_query_timeout_seconds=_float_env("NEO4J_QUERY_TIMEOUT_SECONDS", 30.0),
        llm_provider=llm_provider.strip().lower(),
        gemini_model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
        gemini_temperature=_float_env("GEMINI_TEMPERATURE", 0.2),
        gemini_max_output_tokens=_int_env("GEMINI_MAX_OUTPUT_TOKENS", 2048),
        gemini_api_key=os.environ.get("GEMINI_API_KEY"),
        google_cloud_project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
        google_cloud_location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
        openai_api_key=os.environ.get("OPENAI_API_KEY"),
        graphiti_search_enabled=_bool_env("GRAPHITI_SEARCH_ENABLED", True),
        graphiti_search_limit=_int_env("GRAPHITI_SEARCH_LIMIT", 10),
        default_query_limit=_int_env("KG_QUERY_LIMIT", 20),
        schema_pattern_limit=_int_env("KG_SCHEMA_PATTERN_LIMIT", 50),
        max_rows_for_answer=_int_env("KG_MAX_ROWS_FOR_ANSWER", 30),
        max_history_turns=_int_env("KG_MAX_HISTORY_TURNS", 6),
        cors_allowed_origins=_list_env("CORS_ALLOWED_ORIGINS", ["*"]),
    )


def _load_env_files(base_dir: Path) -> None:
    try:
        from dotenv import load_dotenv
    except Exception:
        return

    local_env = base_dir / ".env"
    if local_env.exists():
        load_dotenv(local_env, override=True)

    parent_env = base_dir.parent / ".env"
    if parent_env.exists():
        load_dotenv(parent_env, override=False)

    graphiti_env = base_dir.parent / "knowledge-graph-integration" / ".env"
    if graphiti_env.exists():
        load_dotenv(graphiti_env, override=False)


def _int_env(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _bool_env(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _list_env(name: str, default: list[str]) -> list[str]:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    if value.strip() == "*":
        return ["*"]
    return [part.strip() for part in value.split(",") if part.strip()]
