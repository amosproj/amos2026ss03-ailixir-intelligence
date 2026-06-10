from __future__ import annotations

from dataclasses import dataclass

from kg_chat.config import AppConfig
from kg_chat.llm import LlmClient
from kg_chat.models import ChatResponse, QueryDebug, QueryPlan, QueryResponse
from kg_chat.neo4j_client import Neo4jGraphClient
from kg_chat.prompts import build_answer_prompt
from kg_chat.query import generate_query_plan, validate_query_plan


@dataclass
class HistoryTurn:
    question: str
    answer: str


class InMemoryHistory:
    def __init__(self, max_turns: int) -> None:
        self.max_turns = max_turns
        self._turns: dict[str, list[HistoryTurn]] = {}

    def format(self, session_id: str) -> str:
        turns = self._turns.get(session_id, [])[-self.max_turns :]
        if not turns:
            return ""
        lines: list[str] = []
        for turn in turns:
            lines.append(f"user: {turn.question}")
            lines.append(f"assistant: {turn.answer}")
        return "\n".join(lines)

    def append(self, session_id: str, *, question: str, answer: str) -> None:
        turns = self._turns.setdefault(session_id, [])
        turns.append(HistoryTurn(question=question, answer=answer))
        del turns[: max(0, len(turns) - self.max_turns)]


class GraphChatService:
    def __init__(
        self,
        *,
        config: AppConfig,
        llm: LlmClient,
        graph_client: Neo4jGraphClient,
    ) -> None:
        self.config = config
        self.llm = llm
        self.graph_client = graph_client
        self.history = InMemoryHistory(max_turns=config.max_history_turns)

    def generate_query_only(self, *, question: str, session_id: str) -> QueryResponse:
        schema = self.graph_client.get_schema()
        history_text = self.history.format(session_id)
        plan = self._generate_validated_plan(question, history_text)
        validated = validate_query_plan(
            plan=plan,
            schema=schema,
            default_limit=self.config.default_query_limit,
        )
        return QueryResponse(
            cypher=validated.cypher,
            parameters=validated.parameters,
            reason=plan.reason,
        )

    def chat(
        self,
        *,
        question: str,
        session_id: str,
        include_debug: bool,
    ) -> ChatResponse:
        schema = self.graph_client.get_schema()
        history_text = self.history.format(session_id)
        plan = self._generate_validated_plan(question, history_text)
        validated = validate_query_plan(
            plan=plan,
            schema=schema,
            default_limit=self.config.default_query_limit,
        )
        rows = self.graph_client.run_read_query(
            validated.cypher,
            validated.parameters,
            max_rows=self.config.max_rows_for_answer,
        )

        answer_prompt = build_answer_prompt(
            question=question,
            history_text=history_text,
            cypher=validated.cypher,
            rows=rows,
        )
        answer = self.llm.generate_text(answer_prompt)
        self.history.append(session_id, question=question, answer=answer)

        debug = None
        if include_debug:
            debug = QueryDebug(
                generated_cypher=validated.generated_cypher,
                executed_cypher=validated.cypher,
                parameters=validated.parameters,
                rows=rows,
                schema_refreshed_at=schema.refreshed_at,
                reason=plan.reason,
            )

        return ChatResponse(answer=answer, session_id=session_id, debug=debug)

    def refresh_schema(self) -> dict:
        return self.graph_client.refresh_schema().to_dict()

    def _generate_validated_plan(self, question: str, history_text: str) -> QueryPlan:
        schema = self.graph_client.get_schema()
        plan = generate_query_plan(
            llm=self.llm,
            question=question,
            schema=schema,
            history_text=history_text,
            default_limit=self.config.default_query_limit,
        )
        validate_query_plan(
            plan=plan,
            schema=schema,
            default_limit=self.config.default_query_limit,
        )
        return plan
