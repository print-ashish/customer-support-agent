import operator
from typing import TypedDict, Annotated, Sequence
from langchain_core.messages import BaseMessage

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    user_id: int
    order_id: int | None
    order_status: str | None
    refund_eligible: bool | None
    escalated: bool

    context: str | None
