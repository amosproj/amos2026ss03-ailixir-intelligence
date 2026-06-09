import json
import os

import vertexai
from vertexai.preview.generative_models import (
    GenerativeModel,
    GenerationConfig,
)

from langchain_core.messages import AIMessage

from graph.state import AgentState

# --------------------------------------------------
# Vertex AI setup
# --------------------------------------------------

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")

GEMINI_MODEL = "gemini-2.5-flash"
TEMPERATURE = 0.4

vertexai.init(project=PROJECT_ID, location=LOCATION)

model = GenerativeModel(model_name=GEMINI_MODEL)

# --------------------------------------------------
# Load documents (mock retrieval source)
# --------------------------------------------------

DATA_FILE = "documents.json"


def load_documents():
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)


DOCUMENTS = load_documents()

# --------------------------------------------------
# LLM helper
# --------------------------------------------------


def call_llm(prompt: str) -> str:
    response = model.generate_content(
        prompt,
        generation_config=GenerationConfig(
            temperature=TEMPERATURE,
            max_output_tokens=1024,
        ),
    )
    return response.text.strip()


# --------------------------------------------------
# Retrieval (simple keyword baseline)
# --------------------------------------------------


def retrieve_context(query: str, top_k: int = 3) -> str:
    query_words = set(query.lower().split())
    scored = []

    for doc in DOCUMENTS:
        hits = sum(1 for w in query_words if w in doc["content"].lower())
        if hits > 0:
            scored.append((hits, doc))

    scored.sort(key=lambda x: x[0], reverse=True)
    top_docs = [d for _, d in scored[:top_k]] or DOCUMENTS[:top_k]

    return "\n\n---\n\n".join(f"[{d['title']}]\n{d['content']}" for d in top_docs)


# --------------------------------------------------
# Helper: extract message history as text
# --------------------------------------------------


def get_history_text(messages):
    return "\n".join([f"{m.type}: {m.content}" for m in messages[-6:]])


# ==================================================
# NODE 0: Guardrail
# ==================================================

BLOCKED_PATTERNS = [
    "ignore previous",
    "ignore all instructions",
    "pretend you",
    "you are now",
    "jailbreak",
    "system prompt",
    "disregard your instructions",
    "act as if",
    "forget your rules",
]

REFUSAL_MESSAGE = (
    "I can only answer questions about the uploaded pharmaceutical documents. "
    "Please ask a relevant question."
)


def guardrail_node(state: AgentState):
    q = state["question"].lower()

    # Block prompt injection / jailbreak attempts
    if any(pattern in q for pattern in BLOCKED_PATTERNS):
        return {
            "answer": REFUSAL_MESSAGE,
            "intent": "BLOCKED",
            "messages": [AIMessage(content=REFUSAL_MESSAGE)],
        }

    # Block obviously off-topic queries (no pharma/medical keywords at all)
    # This is a lightweight heuristic — replace with a classifier for production
    pharma_keywords = [
        "drug",
        "medicine",
        "patient",
        "dose",
        "side effect",
        "interaction",
        "contraindication",
        "trial",
        "clinical",
        "treatment",
        "diabetes",
        "warfarin",
        "metformin",
        "aspirin",
        "bleeding",
        "adverse",
        "hba1c",
        "summarize",
        "summary",
        "explain",
        "what",
        "how",
        "why",
        "when",
        "document",
        "report",
        "tell",
        "describe",
    ]
    if not any(kw in q for kw in pharma_keywords):
        return {
            "answer": REFUSAL_MESSAGE,
            "intent": "BLOCKED",
            "messages": [AIMessage(content=REFUSAL_MESSAGE)],
        }

    # Passed — continue to intent detection
    return {}


# ==================================================
# NODE 1: Intent Detection
# ==================================================


def detect_intent_node(state: AgentState):

    if len(state["messages"]) <= 1:
        return {"intent": "NEW_QUESTION"}

    history_text = get_history_text(state["messages"])

    prompt = f"""
You are an intent classifier.

Conversation:
{history_text}

Latest Question:
{state["question"]}

Return ONLY one label:
- NEW_QUESTION
- FOLLOWUP
"""

    intent = call_llm(prompt)
    intent = "FOLLOWUP" if "FOLLOWUP" in intent.upper() else "NEW_QUESTION"

    return {"intent": intent}


# ==================================================
# NODE 2: Query Rewriter (for follow-ups)
# ==================================================


def rewrite_question_node(state: AgentState):

    history_text = get_history_text(state["messages"])

    prompt = f"""
Rewrite the question so it is fully understandable
without conversation history.

Conversation:
{history_text}

Question:
{state["question"]}

Return ONLY the rewritten question.
"""

    rewritten = call_llm(prompt)
    return {"rewritten_question": rewritten}


# ==================================================
# NODE 3: Retrieval
# ==================================================


def retrieve_node(state: AgentState):
    query = state["rewritten_question"] or state["question"]
    context = retrieve_context(query)
    return {"context": context}


# ==================================================
# NODE 4: Answer Generation
# ==================================================


def answer_node(state: AgentState):

    query = state["rewritten_question"] or state["question"]
    history_text = get_history_text(state["messages"])

    prompt = f"""
You are AIlixir, an AI assistant specialising in pharmaceutical documents.

Use ONLY the provided context to answer. Do not use outside knowledge.
If the answer is not present in the context, say "I don't know based on the documents."

Context:
{state["context"]}

Conversation:
{history_text}

Question:
{query}
"""

    answer = call_llm(prompt)
    return {"answer": answer, "messages": [AIMessage(content=answer)]}
