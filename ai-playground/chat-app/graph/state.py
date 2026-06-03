from typing import TypedDict, Annotated

from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]

    question: str

    intent: str

    rewritten_question: str

    context: str

    answer: str
