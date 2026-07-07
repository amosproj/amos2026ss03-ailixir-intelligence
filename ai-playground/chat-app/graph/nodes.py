"""
graph/nodes.py
--------------
Pure pipeline functions — no LangGraph, no Postgres, no session state.
The frontend owns history. We receive it, use it, done.

Pipeline order (called by main.py):
  1. run_guardrail    — block bad questions before any heavy LLM work
  2. classify_intent  — NEW_QUESTION or FOLLOWUP?
  3. rewrite_question — FOLLOWUP only: resolve pronouns into a full query
  4. retrieve_context — vector RAG search over documents.json (see
                         graph/vector_store.py), falling back to keyword
                         search if the embedding call fails
  5. generate_answer  — Gemini produces the final answer
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import vertexai
from dotenv import load_dotenv
from vertexai.preview.generative_models import GenerationConfig, GenerativeModel

from graph import vector_store

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ---------------------------------------------------------------------------
# Vertex AI
# ---------------------------------------------------------------------------

PROJECT_ID   = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("VERTEX_PROJECT")
LOCATION     = os.getenv("GOOGLE_CLOUD_LOCATION") or os.getenv("VERTEX_LOCATION", "us-central1")
GEMINI_MODEL = "gemini-2.5-flash"
TEMPERATURE  = 0.4

vertexai.init(project=PROJECT_ID, location=LOCATION)
_model = GenerativeModel(model_name=GEMINI_MODEL)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REFUSAL_MESSAGE = (
    "I can only answer questions about pharmaceutical documents. "
    "Please ask something related to the uploaded materials."
)

# Patterns that indicate prompt injection / jailbreak attempts.
# Checked with a simple substring match — no LLM needed.
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

# Phrases that strongly signal a follow-up without needing the LLM classifier.
FOLLOWUP_SIGNALS: list[str] = [
    "follow up", "followup", "follow-up",
    "what about it", "what about them", "what about that", "what about this",
    "tell me more about it", "tell me more about that", "tell me more about this",
    "more about it", "more about this", "more about that",
    "what else about it", "what else about that",
    "tell me more",
    "expand on",
    "elaborate on",
]

# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------


def _call_llm(prompt: str, max_tokens: int = 1024) -> str:
    """Single wrapper for all synchronous (non-streaming) Gemini calls."""
    response = _model.generate_content(
        prompt,
        generation_config=GenerationConfig(
            temperature=TEMPERATURE,
            max_output_tokens=max_tokens,
        ),
    )
    return response.text.strip()


# ---------------------------------------------------------------------------
# Shared utility — used by every step that needs history as plain text
# ---------------------------------------------------------------------------


def history_to_text(chat_history: list[dict]) -> str:
    """
    Convert [{role, content}, ...] to a plain-text block for prompt insertion.

    Only complete user → assistant pairs are kept. Orphaned messages
    (a user message with no assistant reply, or an assistant message at the
    start) are silently dropped so every downstream prompt sees clean context.

    Example output:
      User: What are the side effects of Metformin?
      Assistant: Common side effects include nausea, diarrhoea...
      User: What is the maximum dose?
      Assistant: The maximum daily dose is 2000–2500 mg.
    """
    lines: list[str] = []
    i = 0
    while i < len(chat_history):
        msg  = chat_history[i]
        role = msg.get("role", "")

        if role == "user":
            next_msg = chat_history[i + 1] if i + 1 < len(chat_history) else None
            if next_msg and next_msg.get("role") == "assistant":
                lines.append(f"User: {msg.get('content', '').strip()}")
                lines.append(f"Assistant: {next_msg.get('content', '').strip()}")
                i += 2
            else:
                i += 1  # incomplete pair — skip
        else:
            i += 1  # leading assistant message — skip

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Step 1 — Guardrail
# ---------------------------------------------------------------------------


def run_guardrail(question: str) -> str | None:
    """
    Returns REFUSAL_MESSAGE if the question should be blocked, else None.

    Two-stage check:
      Stage A — fast pattern match (no LLM, no cost):
        Catches prompt injection and jailbreak attempts instantly.

      Stage B — LLM off-topic classifier:
        Rejects questions unrelated to pharmaceutical documents.
        max_tokens=100 gives gemini-2.5-flash enough room for its
        internal thinking tokens (~7) before emitting the one-word verdict.
    """
    q_lower = question.lower()

    # Stage A — pattern match
    if any(pattern in q_lower for pattern in BLOCKED_PATTERNS):
        print(f"[guardrail] BLOCKED (pattern match): {question!r}")
        return REFUSAL_MESSAGE

    # Stage B — LLM relevance check
    prompt = f"""You are a content classifier for a pharmaceutical document assistant.

Decide if the following question is relevant to pharmaceutical documents, medicines,
clinical trials, drug interactions, patient data, or document analysis.

Reply with exactly one word: RELEVANT or OFF_TOPIC

Question: {question}"""

    try:
        verdict = _call_llm(prompt, max_tokens=100).upper().strip()
        if "OFF_TOPIC" in verdict:
            print(f"[guardrail] BLOCKED (off-topic): {question!r}")
            return REFUSAL_MESSAGE
    except Exception as exc:
        # On LLM failure, allow through — better to let a borderline question
        # pass than to silently block a real user.
        print(f"[guardrail] LLM check failed ({exc}), allowing through")

    print(f"[guardrail] ALLOWED: {question!r}")
    return None


# ---------------------------------------------------------------------------
# Step 2 — Intent classification
# ---------------------------------------------------------------------------


def classify_intent(question: str, chat_history: list[dict]) -> str:
    """
    Returns "FOLLOWUP" or "NEW_QUESTION".

    Three-stage decision (cheapest first):
      Stage A — no history → NEW_QUESTION immediately, zero LLM cost.
      Stage B — heuristic signal words → FOLLOWUP immediately, zero LLM cost.
      Stage C — LLM classifier for ambiguous cases.
    """
    history_text = history_to_text(chat_history)

    print(f"[intent] history turns: {len(chat_history)}, history_text length: {len(history_text)}")
    print(f"[intent] history_text preview: {repr(history_text[:300]) if history_text else '(empty)'}")

    # Stage A — no history means it can only be a new question
    if not history_text:
        print("[intent] → NEW_QUESTION (no prior history)")
        return "NEW_QUESTION"

    # Stage B — obvious follow-up signal words
    q_lower = question.lower()
    if any(sig in q_lower for sig in FOLLOWUP_SIGNALS):
        print("[intent] → FOLLOWUP (heuristic signal matched)")
        return "FOLLOWUP"

    # Stage C — LLM classifier for ambiguous cases
    prompt = f"""You are an intent classifier for a multi-turn pharmaceutical chat assistant.

Conversation history (oldest first):
{history_text}

New user message: {question}

Decide if the new message is a FOLLOWUP to the conversation above,
or a completely independent NEW_QUESTION about a different topic.

FOLLOWUP: references something already discussed ("it", "this", "that", the same drug/topic),
          asks for more detail, or uses phrases like "what else", "what about", "also".

NEW_QUESTION: introduces a new drug, topic, or document not mentioned before,
              and makes complete sense with zero context from the conversation.

Reply with exactly one word: FOLLOWUP or NEW_QUESTION"""

    try:
        verdict = _call_llm(prompt, max_tokens=100).upper().strip()
        intent  = "FOLLOWUP" if "FOLLOWUP" in verdict else "NEW_QUESTION"
    except Exception:
        intent = "NEW_QUESTION"  # safe fallback

    print(f"[intent] → {intent} (LLM classification)")
    return intent


# ---------------------------------------------------------------------------
# Step 3 — Query rewriter (FOLLOWUP only)
# ---------------------------------------------------------------------------


def rewrite_question(question: str, chat_history: list[dict]) -> str:
    """
    Rewrites a follow-up into a fully self-contained query by resolving
    pronouns and vague references against the conversation history.

    Example:
      History : Q "What are Metformin's side effects?" / A "Nausea, diarrhoea..."
      Follow-up: "What about the dosage?"
      Rewritten: "What is the recommended dosage for Metformin?"
    """
    history_text = history_to_text(chat_history)

    prompt = f"""You are a query rewriter for a pharmaceutical document assistant.

Rewrite the follow-up question as one COMPLETE, self-contained sentence that makes
full sense WITHOUT reading the conversation history.

Rules:
- Output ONLY the rewritten question — no explanation, no preamble
- Must end with a question mark — never cut off mid-sentence
- Replace ALL pronouns (it, this, that, they, them) with the specific subject from history
- Replace vague phrases ("in it", "in this", "the document") with the actual drug/document name
- Keep it natural and concise

Examples:
  History:   Warfarin + Aspirin interaction for Patient A
  Follow-up: "How much is prescribed in it?"
  Rewritten: "How much Warfarin and Aspirin is prescribed for Patient A?"

  History:   Warfarin contraindications including pregnancy
  Follow-up: "What is described about pregnancy in it?"
  Rewritten: "What does the Warfarin contraindications document say about pregnancy?"

Conversation history:
{history_text}

Follow-up question: {question}

Rewritten question:"""

    try:
        rewritten = _call_llm(prompt, max_tokens=200).strip().strip('"').strip("'")
        print(f"[rewrite] '{question}' → '{rewritten}'")
        return rewritten
    except Exception as exc:
        print(f"[rewrite] LLM failed ({exc}), using original question")
        return question


# ---------------------------------------------------------------------------
# Step 4 — Retrieval
# ---------------------------------------------------------------------------

_DATA_FILE  = Path(__file__).resolve().parent.parent / "documents.json"
_documents: list[dict] | None = None


def _load_documents() -> list[dict]:
    """Loads documents.json once and caches it in memory."""
    global _documents
    if _documents is None:
        with open(_DATA_FILE, encoding="utf-8") as f:
            _documents = json.load(f)
    return _documents


def retrieve_context(query: str, top_k: int = 3) -> tuple[str, str]:
    """
    Vector RAG retrieval over documents.json (see graph/vector_store.py).

    Embeds the (rewritten) query and runs a cosine-similarity search over
    pre-computed chunk embeddings — real semantic search rather than
    literal word overlap, so e.g. "how much should someone take" can match
    a chunk about "dosage" even without a shared keyword.

    If the embedding call fails for any reason (no network, no Vertex AI
    quota, model misconfigured, etc.) this falls back to the original
    keyword-overlap search over full documents, so a single embedding
    outage never breaks the whole chat pipeline.

    Returns (context_text, source_label).
    source_label is "vector_rag" (normal path) or "keyword_fallback".
    This is the seam to extend for the knowledge-graph hybrid (issue #187):
    add a kg_store.search() call alongside vector_store.search() here and
    merge the two result sets — the (context, source) contract downstream
    doesn't need to change.
    """
    try:
        hits = vector_store.search(query, top_k=top_k)
        if not hits:
            raise ValueError("vector index is empty")

        context_text = "\n\n---\n\n".join(
            f"[{hit['title']}]\n{hit['text']}" for hit in hits
        )
        scores = [round(hit["score"], 3) for hit in hits]
        print(f"[retrieve] query: {query!r} → {len(hits)} chunk(s) via vector_rag (scores: {scores})")
        return context_text, "vector_rag"

    except Exception as exc:
        print(f"[retrieve] vector search failed ({exc}), falling back to keyword search")
        return _retrieve_context_keyword_fallback(query, top_k)


def _retrieve_context_keyword_fallback(query: str, top_k: int = 3) -> tuple[str, str]:
    """
    Original keyword-overlap retrieval, kept as a safety-net fallback for
    retrieve_context() when embedding-based search is unavailable.
    """
    documents  = _load_documents()
    query_words = set(query.lower().split())

    scored = [
        (sum(1 for w in query_words if w in doc["content"].lower()), doc)
        for doc in documents
    ]
    scored = [(score, doc) for score, doc in scored if score > 0]
    scored.sort(key=lambda x: x[0], reverse=True)

    top_docs = [doc for _, doc in scored[:top_k]] or documents[:top_k]

    context_text = "\n\n---\n\n".join(
        f"[{doc['title']}]\n{doc['content']}" for doc in top_docs
    )
    print(f"[retrieve] query: {query!r} → {len(top_docs)} doc(s) via keyword_fallback")
    return context_text, "keyword_fallback"


# ---------------------------------------------------------------------------
# Step 5 — Answer generation
# ---------------------------------------------------------------------------

_ANSWER_PROMPT = """\
You are AIlixir, an AI assistant specialising in pharmaceutical documents.

Use ONLY the provided context to answer. Do not use outside knowledge.
If the answer is not in the context, say "I don't know based on the documents."

Context:
{context}

Conversation so far:
{history}

Question:
{question}
"""


def build_answer_prompt(context: str, history_text: str, question: str) -> str:
    """
    Builds the final answer prompt.
    Single source of truth — used by generate_answer() (sync)
    and directly by main.py's token_generator() (stream).
    """
    return _ANSWER_PROMPT.format(
        context=context,
        history=history_text,
        question=question,
    )


def generate_answer(context: str, history_text: str, question: str) -> str:
    """Calls Gemini synchronously and returns the complete answer string."""
    prompt = build_answer_prompt(context, history_text, question)
    try:
        answer = _call_llm(prompt)
        print(f"[answer] generated {len(answer)} chars")
        return answer
    except Exception as exc:
        return f"[Error generating answer: {exc}]"