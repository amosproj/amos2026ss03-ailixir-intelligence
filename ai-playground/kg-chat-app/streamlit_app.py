from __future__ import annotations

import uuid
from typing import Any

import requests
import streamlit as st


DEFAULT_API_BASE_URL = "http://127.0.0.1:8010"
DEFAULT_TIMEOUT_SECONDS = 120


st.set_page_config(
    page_title="AIlixir KG Chat",
    page_icon="",
    layout="wide",
)


def get_json(url: str, *, timeout_seconds: int) -> tuple[dict[str, Any] | None, str | None]:
    try:
        response = requests.get(url, timeout=timeout_seconds)
        response.raise_for_status()
        return response.json(), None
    except Exception as exc:
        return None, str(exc)


def post_json(
    url: str,
    payload: dict[str, Any],
    *,
    timeout_seconds: int,
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        response = requests.post(url, json=payload, timeout=timeout_seconds)
        response.raise_for_status()
        return response.json(), None
    except requests.HTTPError as exc:
        detail: Any
        try:
            detail = response.json()
        except Exception:
            detail = response.text
        return None, f"{exc}\n{detail}"
    except Exception as exc:
        return None, str(exc)


def reset_chat() -> None:
    st.session_state.messages = []
    st.session_state.session_id = f"streamlit-{uuid.uuid4().hex[:8]}"


if "session_id" not in st.session_state:
    st.session_state.session_id = f"streamlit-{uuid.uuid4().hex[:8]}"

if "messages" not in st.session_state:
    st.session_state.messages = []


with st.sidebar:
    st.header("Connection")
    api_base_url = st.text_input("API base URL", value=DEFAULT_API_BASE_URL).rstrip("/")
    session_id = st.text_input("Session ID", value=st.session_state.session_id)
    st.session_state.session_id = session_id
    group_id = st.text_input(
        "Neo4j group_id",
        value=st.session_state.get("group_id", ""),
        placeholder="Optional Graphiti group_id",
    ).strip()
    st.session_state.group_id = group_id
    timeout_seconds = st.number_input(
        "Request timeout seconds",
        min_value=10,
        max_value=300,
        value=DEFAULT_TIMEOUT_SECONDS,
        step=10,
    )
    include_debug = st.toggle("Show query debug", value=True)

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("Health", use_container_width=True):
            health, error = get_json(
                f"{api_base_url}/health",
                timeout_seconds=timeout_seconds,
            )
            st.session_state.health = health
            st.session_state.health_error = error
    with col_b:
        if st.button("Reset", use_container_width=True):
            reset_chat()
            st.rerun()

    health = st.session_state.get("health")
    health_error = st.session_state.get("health_error")
    if health_error:
        st.error(health_error)
    elif health:
        status = health.get("status", "unknown")
        if status == "ok":
            st.success("Backend ready")
        else:
            st.warning("Backend degraded")
        st.json(health, expanded=False)

    with st.expander("Schema preview"):
        if st.button("Load schema", use_container_width=True):
            schema, error = get_json(
                f"{api_base_url}/schema",
                timeout_seconds=timeout_seconds,
            )
            st.session_state.schema = schema
            st.session_state.schema_error = error

        schema_error = st.session_state.get("schema_error")
        schema = st.session_state.get("schema")
        if schema_error:
            st.error(schema_error)
        elif schema:
            labels = schema.get("labels", [])
            relationships = schema.get("relationship_types", [])
            st.caption(f"{len(labels)} labels, {len(relationships)} relationship types")
            st.json(schema, expanded=False)


st.title("AIlixir Knowledge Graph Chat")
st.caption("Ask questions against your Neo4j graph through the FastAPI KG chat backend.")

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        debug = message.get("debug")
        if debug:
            with st.expander("Query debug"):
                planner_debug = debug.get("planner_debug") or {}
                planner_raw = planner_debug.get("raw_response")
                if planner_raw:
                    st.caption("Planner LLM JSON")
                    st.code(planner_raw, language="json")
                st.code(
                    debug.get("executed_cypher")
                    or debug.get("generated_cypher")
                    or "",
                    language="cypher",
                )
                st.json(
                    {
                        "intent": debug.get("intent"),
                        "strategy": debug.get("strategy"),
                        "selected_solution": planner_debug.get("selected_solution"),
                        "route_plan": debug.get("route_plan"),
                        "planner_debug": planner_debug,
                        "retrieval_debug": debug.get("retrieval_debug"),
                        "graphiti_search_results": debug.get("graphiti_search_results"),
                        "parameters": debug.get("parameters"),
                        "reason": debug.get("reason"),
                        "rows": debug.get("rows"),
                        "schema_refreshed_at": debug.get("schema_refreshed_at"),
                    },
                    expanded=False,
                )


prompt = st.chat_input("Ask your knowledge graph...")
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    payload = {
        "question": prompt,
        "session_id": st.session_state.session_id,
        "group_id": st.session_state.get("group_id") or None,
        "include_debug": include_debug,
    }

    with st.chat_message("assistant"):
        with st.spinner("Querying graph and generating answer..."):
            data, error = post_json(
                f"{api_base_url}/chat",
                payload,
                timeout_seconds=timeout_seconds,
            )

        if error:
            answer = f"Backend error:\n\n```text\n{error}\n```"
            st.markdown(answer)
            st.session_state.messages.append({"role": "assistant", "content": answer})
        else:
            answer = data.get("answer", "")
            st.markdown(answer)
            debug = data.get("debug")
            if debug:
                with st.expander("Query debug"):
                    planner_debug = debug.get("planner_debug") or {}
                    planner_raw = planner_debug.get("raw_response")
                    if planner_raw:
                        st.caption("Planner LLM JSON")
                        st.code(planner_raw, language="json")
                    st.code(
                        debug.get("executed_cypher")
                        or debug.get("generated_cypher")
                        or "",
                        language="cypher",
                    )
                    st.json(
                        {
                            "intent": debug.get("intent"),
                            "strategy": debug.get("strategy"),
                            "selected_solution": planner_debug.get("selected_solution"),
                            "route_plan": debug.get("route_plan"),
                            "planner_debug": planner_debug,
                            "retrieval_debug": debug.get("retrieval_debug"),
                            "graphiti_search_results": debug.get("graphiti_search_results"),
                            "parameters": debug.get("parameters"),
                            "reason": debug.get("reason"),
                            "rows": debug.get("rows"),
                            "schema_refreshed_at": debug.get("schema_refreshed_at"),
                        },
                        expanded=False,
                    )
            st.session_state.messages.append(
                {"role": "assistant", "content": answer, "debug": debug}
            )
