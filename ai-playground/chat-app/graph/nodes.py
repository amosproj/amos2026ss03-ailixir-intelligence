"""
graph/nodes.py
--------------
Every node in the LangGraph pipeline lives here.
main.py imports constants and helpers — it does NOT duplicate any logic.

Node execution order (wired in builder.py):
  guardrail_node → intent_node → rewrite_node → retrieve_node → answer_node
                                                                 ↑ skipped when
                                                                   state.streaming=True

KG integration note (issue #75)
--------------------------------
To swap in knowledge-graph retrieval, replace the body of `_retrieve_from_documents`
with your KG client call, or add a second function `_retrieve_from_kg` and route
between them inside `retrieve_node` based on a config flag or the query itself.
No other file needs to change.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Literal

import vertexai
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage
from vertexai.preview.generative_models import GenerativeModel, GenerationConfig

from graph.state import AgentState

# Load .env from ai-playground/ (two levels up from graph/nodes.py)
# Safe to call multiple times — load_dotenv is idempotent.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ---------------------------------------------------------------------------
# Vertex AI — initialised once when the module is imported
# ---------------------------------------------------------------------------

# Env var names match BOTH the new .env keys AND Google Cloud conventions.
# GOOGLE_CLOUD_PROJECT is the standard name used by all Google Cloud SDKs.
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("VERTEX_PROJECT")
LOCATION   = os.getenv("GOOGLE_CLOUD_LOCATION") or os.getenv("VERTEX_LOCATION", "us-central1")
GEMINI_MODEL = "gemini-2.5-flash"
TEMPERATURE  = 0.4

vertexai.init(project=PROJECT_ID, location=LOCATION)
_model = GenerativeModel(model_name=GEMINI_MODEL)

# ---------------------------------------------------------------------------
# Guardrail constants  (imported by main.py — single source of truth)
# ---------------------------------------------------------------------------

REFUSAL_MESSAGE = (
    "I can only answer questions about pharmaceutical documents. "
    "Please ask something related to the uploaded materials."
)

# Patterns that indicate prompt-injection or jailbreak attempts
BLOCKED_PATTERNS: list[str] = [
    "ignore previous",
    "ignore all previous",
    "disregard",
    "forget your instructions",
    "pretend you are",
    "act as",
    "jailbreak",
    "dan mode",
    "developer mode",
    "bypass",
    "override instructions",
    "new persona",
    "you are now",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_messages(messages: list) -> list:
    """
    Remove malformed history entries so the intent classifier always sees
    proper User → Assistant pairs.

    Problem this solves
    -------------------
    If a previous version of answer_node saved only AIMessage (no preceding
    HumanMessage), the history starts with "Assistant: ..." which confuses
    the LLM classifier — it thinks there is no prior user context and returns
    NEW_QUESTION even for obvious follow-ups.

    Strategy: walk the list and only keep a HumanMessage if it is followed by
    an AIMessage (i.e. a complete Q+A pair). Orphaned AIMessages at the start
    are dropped entirely. This is safe to call on well-formed history too —
    it is a no-op when all pairs are correct.
    """
    cleaned: list = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        if isinstance(msg, HumanMessage):
            # Look ahead for the matching AIMessage
            if i + 1 < len(messages) and isinstance(messages[i + 1], AIMessage):
                cleaned.append(msg)
                cleaned.append(messages[i + 1])
                i += 2
            else:
                # Human with no following AI — skip (incomplete pair)
                i += 1
        elif isinstance(msg, AIMessage) and not cleaned:
            # Leading orphan AI message (from old broken saves) — drop it
            i += 1
        else:
            # Anything else mid-stream: keep and move on
            cleaned.append(msg)
            i += 1
    return cleaned


def get_history_text(messages: list) -> str:
    """
    Convert a list of LangChain messages into a plain-text conversation block
    suitable for insertion into a prompt. Cleans malformed pairs first.
    """
    clean = _clean_messages(messages)
    lines: list[str] = []
    for msg in clean:
        if isinstance(msg, HumanMessage):
            lines.append(f"User: {msg.content}")
        elif isinstance(msg, AIMessage):
            lines.append(f"Assistant: {msg.content}")
    return "\n".join(lines)


def _call_llm(prompt: str, max_tokens: int = 1024) -> str:
    """Single wrapper for all non-streaming Gemini calls in this file."""
    response = _model.generate_content(
        prompt,
        generation_config=GenerationConfig(
            temperature=TEMPERATURE,
            max_output_tokens=max_tokens,
        ),
    )
    return response.text.strip()


# ---------------------------------------------------------------------------
# Document retrieval (replace this section for KG integration — issue #75)
# ---------------------------------------------------------------------------

_DATA_FILE = Path(__file__).resolve().parent.parent / "documents.json"
_documents: list[dict] | None = None   # lazy-loaded once


def _load_documents() -> list[dict]:
    global _documents
    if _documents is None:
        with open(_DATA_FILE, encoding="utf-8") as f:
            _documents = json.load(f)
    return _documents


def retrieve_context(query: str, top_k: int = 3) -> tuple[str, str]:
    """
    Keyword search over documents.json.

    Returns
    -------
    (context_text, source_label)
        context_text  — concatenated document passages for the LLM prompt
        source_label  — "documents.json"  (will be "knowledge_graph" after #75)

    KG swap point
    -------------
    Replace this function's body with your KG client call.
    The return signature (context_text, source_label) must stay the same
    so retrieve_node and the streaming path in main.py both work unchanged.
    """
    documents = _load_documents()
    query_words = set(query.lower().split())
    scored: list[tuple[int, dict]] = []

    for doc in documents:
        hits = sum(1 for word in query_words if word in doc["content"].lower())
        if hits > 0:
            scored.append((hits, doc))

    scored.sort(key=lambda x: x[0], reverse=True)
    top_docs = [doc for _, doc in scored[:top_k]] or documents[:top_k]

    context_text = "\n\n---\n\n".join(
        f"[{doc['title']}]\n{doc['content']}" for doc in top_docs
    )
    return context_text, "documents.json"


# ---------------------------------------------------------------------------
# Node 1 — Guardrail
# ---------------------------------------------------------------------------

def guardrail_node(state: AgentState) -> dict:
    """
    Checks the question for:
      1. Prompt-injection patterns (BLOCKED_PATTERNS list)
      2. Off-topic intent — uses the LLM for robust classification instead of
         a brittle keyword allowlist

    Sets intent="BLOCKED" and fills answer with REFUSAL_MESSAGE if blocked.
    The graph routes to END immediately in that case (see builder.py).

    NOTE: this is the ONE place guardrail logic lives.
    main.py must NOT duplicate this check.
    """
    question = state["question"]
    q_lower  = question.lower()

    # Fast path: injection pattern match (no LLM call needed)
    if any(pattern in q_lower for pattern in BLOCKED_PATTERNS):
        return {
            "intent": "BLOCKED",
            "answer": REFUSAL_MESSAGE,
        }

    # LLM-based relevance check — much more robust than a keyword allowlist
    # Classifies as RELEVANT or OFF_TOPIC; avoids false-blocking general
    # questions like "summarize the document" or "my brother broke his leg".
    classification_prompt = f"""You are a content classifier for a pharmaceutical document assistant.

Decide if the following question is relevant to pharmaceutical documents, medicines,
clinical trials, drug interactions, patient data, or document analysis.

Reply with exactly one word: RELEVANT or OFF_TOPIC

Question: {question}"""

    try:
        verdict = _call_llm(classification_prompt, max_tokens=10).upper().strip()
        # Be lenient: only block if explicitly OFF_TOPIC
        if "OFF_TOPIC" in verdict:
            return {
                "intent": "BLOCKED",
                "answer": REFUSAL_MESSAGE,
            }
    except Exception:
        # If the LLM call fails, allow the question through rather than
        # silently blocking legitimate users
        pass

    return {}   # no changes to state — proceed to intent_node


# ---------------------------------------------------------------------------
# Node 2 — Intent detection
# ---------------------------------------------------------------------------

def intent_node(state: AgentState) -> dict:
    """
    Classifies the question as NEW_QUESTION or FOLLOWUP.
    FOLLOWUP triggers the rewrite node; NEW_QUESTION skips it.

    LangGraph merges the persisted messages from the checkpoint into the state
    BEFORE the graph runs, so state["messages"] already contains the full
    conversation history from previous turns when this node executes.
    We exclude the last two entries (current turn's Human+AI) if they were
    accidentally pre-populated, but in practice the messages list contains
    only prior turns at this point.
    """
    messages = state.get("messages", [])

    # Filter to only prior-turn messages — exclude any that match the
    # current question (which hasn't been answered yet so won't be there,
    # but guard defensively)
    prior_messages = [
        m for m in messages
        if not (isinstance(m, HumanMessage) and m.content == state["question"])
    ]

    history_text = get_history_text(prior_messages)

    # Log so you can see what the node actually receives
    print(f"[intent_node] messages in state: {len(messages)}, prior: {len(prior_messages)}")
    print(f"[intent_node] history_text: {repr(history_text[:200]) if history_text else '(empty)'}")

    # ── Heuristic first — runs regardless of history quality ─────────────────
    # If the question contains explicit follow-up language, classify it as
    # FOLLOWUP immediately. This is robust even when stored history is malformed
    # (all AIMessage, no UserMessage) or Postgres has been corrupted.
    # Heuristic: only fire on UNAMBIGUOUS follow-up markers.
    # Do NOT include: "in it", "described in", "mentioned in", "also", "what else"
    # — these appear in new questions too ("What is described in the first document?")
    # Only markers that make ZERO sense in a standalone new question are kept here.
    FOLLOWUP_SIGNALS = [
        "follow up", "followup", "follow-up",
        "another followup", "another follow-up",
        "what about that", "what about this",
        "more about it", "more about this", "more about that",
        "tell me more",
        "expand on",
        "elaborate on",
    ]
    q_lower = state["question"].lower()
    if any(sig in q_lower for sig in FOLLOWUP_SIGNALS) and history_text:
        # Only fire heuristic if there IS history — a "follow up" with zero
        # history is still a new question
        print(f"[intent_node] → FOLLOWUP (heuristic matched + history present)")
        return {"intent": "FOLLOWUP", "rewritten_question": ""}

    if not history_text:
        # No usable prior conversation after cleaning — new question
        print("[intent_node] → NEW_QUESTION (no clean history)")
        return {"intent": "NEW_QUESTION", "rewritten_question": state["question"]}

    prompt = f"""You are an intent classifier for a multi-turn pharmaceutical chat assistant.

Conversation history (most recent last):
{history_text}

New user message: {state['question']}

Task: decide if the new message is a FOLLOWUP to the conversation above,
or a completely independent NEW_QUESTION about a different topic.

A message is FOLLOWUP if it:
- References something from the conversation (uses "it", "this", "that", "the document", etc.)
- Asks for more detail about a previously discussed topic
- Uses phrases like "what else", "what about", "also", "additionally"

A message is NEW_QUESTION if it:
- Introduces an entirely new drug, topic, or document not discussed before
- Could be understood with zero context from this conversation

Reply with exactly one word: FOLLOWUP or NEW_QUESTION"""

    try:
        verdict = _call_llm(prompt, max_tokens=10).upper().strip()
        intent: Literal["FOLLOWUP", "NEW_QUESTION"] = (
            "FOLLOWUP" if "FOLLOWUP" in verdict else "NEW_QUESTION"
        )
    except Exception:
        intent = "NEW_QUESTION"

    print(f"[intent_node] → {intent}")
    return {
        "intent": intent,
        # rewritten_question filled by rewrite_node if FOLLOWUP,
        # left as original if NEW_QUESTION
        "rewritten_question": state["question"] if intent == "NEW_QUESTION" else "",
    }


# ---------------------------------------------------------------------------
# Node 3 — Query rewriter  (only runs for FOLLOWUP)
# ---------------------------------------------------------------------------

def rewrite_node(state: AgentState) -> dict:
    """
    Rewrites a follow-up question into a fully self-contained query by
    resolving pronouns, "it", "this", "that", "the document", etc.

    Example:
      History: Q: "What are Metformin's side effects?"
               A: "Nausea, diarrhoea, lactic acidosis..."
      Follow-up: "What about the dosage?"
      Rewritten: "What is the recommended dosage for Metformin?"

    Example:
      History: Q: "What is described in the document?"
               A: "The document describes Type 2 diabetes treatment..."
      Follow-up: "What type of diabetes is described in it?"
      Rewritten: "What type of diabetes is described in the pharmaceutical document about Metformin?"
    """
    messages = state.get("messages", [])
    # Exclude the current unanswered question if it somehow ended up in state,
    # then clean malformed pairs before building history text
    prior_messages = [
        m for m in messages
        if not (isinstance(m, HumanMessage) and m.content == state["question"])
    ]
    history_text = get_history_text(prior_messages)  # get_history_text cleans internally

    prompt = f"""You are a query rewriter for a pharmaceutical document assistant.

Your job: take a follow-up question and rewrite it as one COMPLETE sentence that makes full
sense WITHOUT reading the conversation history.

Rules:
- The rewritten question must be a COMPLETE sentence ending with a question mark
- Replace ALL pronouns (it, this, that, they, them) with the specific subject from the history
- Replace vague references like "in it", "in this", "the document" with the actual drug/document name
- Keep the rewritten question natural and concise
- Output ONLY the rewritten question — no explanation, no preamble, no partial sentences

Examples:
  History: talked about Warfarin and Aspirin interaction for Patient A
  Follow-up: "How much is prescribed in it?"
  Rewritten: "How much Warfarin and Aspirin is prescribed for Patient A?"

  History: discussed Warfarin contraindications including pregnancy
  Follow-up: "What is described about pregnancy in it?"
  Rewritten: "What is described about pregnancy in the Warfarin contraindications document?"

Conversation history:
{history_text}

Follow-up question: {state['question']}

Rewritten question (complete sentence, ends with ?):"""

    try:
        rewritten = _call_llm(prompt, max_tokens=200)
        # Strip any accidental preamble the model might add
        rewritten = rewritten.strip().strip('"').strip("'")
        print(f"[rewrite_node] '{state['question']}' → '{rewritten}'")
    except Exception:
        rewritten = state["question"]   # fallback: use original

    return {"rewritten_question": rewritten}


# ---------------------------------------------------------------------------
# Node 4 — Retrieval
# ---------------------------------------------------------------------------

def retrieve_node(state: AgentState) -> dict:
    """
    Retrieves relevant context for the (possibly rewritten) question.

    The actual retrieval logic is in `retrieve_context()` above — that is
    the only function that changes when KG integration lands (issue #75).
    """
    query = state.get("rewritten_question") or state["question"]
    context_text, source_label = retrieve_context(query)

    return {
        "context": context_text,
        "source":  source_label,
    }


# ---------------------------------------------------------------------------
# Node 5 — Answer  (skipped when state.streaming=True)
# ---------------------------------------------------------------------------

_ANSWER_PROMPT_TEMPLATE = """\
You are AIlixir, an AI assistant specialising in pharmaceutical documents.

Use ONLY the provided context to answer. Do not use outside knowledge.
If the answer is not present in the context, say "I don't know based on the documents."

Context:
{context}

Conversation:
{history}

Question:
{question}
"""


def answer_node(state: AgentState) -> dict:
    """
    Generates the final answer using Gemini.

    This node is SKIPPED when state.streaming=True — in that case main.py
    calls Gemini directly with stream=True using the same prompt template
    (build_answer_prompt) so there is no duplication.
    """
    prompt = build_answer_prompt(
        context=state.get("context", ""),
        history_text=get_history_text(state.get("messages", [])),
        question=state.get("rewritten_question") or state["question"],
    )

    try:
        answer = _call_llm(prompt)
    except Exception as exc:
        answer = f"[Error generating answer: {exc}]"

    # Save the REWRITTEN question (not raw) as the human message so that
    # the next turn's intent_node and rewrite_node see fully resolved history.
    # e.g. "What about dosage?" becomes "What is the dosage for Metformin?"
    saved_question = state.get("rewritten_question") or state["question"]

    return {
        "answer": answer,
        "messages": [
            HumanMessage(content=saved_question),
            AIMessage(content=answer),
        ],
    }


def build_answer_prompt(context: str, history_text: str, question: str) -> str:
    """
    Exported so main.py can build the IDENTICAL prompt for streaming
    without duplicating the template string.
    This is the single source of truth for the answer prompt.
    """
    return _ANSWER_PROMPT_TEMPLATE.format(
        context=context,
        history=history_text,
        question=question,
    )