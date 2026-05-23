from typing import Annotated

from langchain_core.tools import tool, InjectedToolArg
from langchain_core.runnables import RunnableConfig
from rag.retriever import search_faq as retrieve_faq
from db.session import async_session_maker
from db.models import Order, Escalation, Message as DBMessage, Conversation
from sqlalchemy import select


def _user_id(config: RunnableConfig) -> int | None:
    return config.get("configurable", {}).get("user_id")


def _conversation_id(config: RunnableConfig) -> int | None:
    return config.get("configurable", {}).get("conversation_id")


@tool
async def get_order_status(
    order_id: int,
    config: Annotated[RunnableConfig, InjectedToolArg()],
) -> str:
    """Check the status of a specific order."""
    user_id = _user_id(config)
    if not user_id:
        return "Error: User ID not found in context."

    async with async_session_maker() as db:
        result = await db.execute(
            select(Order).filter(Order.id == order_id, Order.user_id == user_id)
        )
        order = result.scalars().first()
        if not order:
            return f"Order {order_id} not found or doesn't belong to this user."

        eligible = "yes" if order.days_since_delivery and order.days_since_delivery <= 30 else "no"
        return f"Order {order_id} status: {order.status}. Eligible for refund: {eligible}."


@tool
async def process_refund(
    order_id: int,
    config: Annotated[RunnableConfig, InjectedToolArg()],
) -> str:
    """Process a refund for a given order if eligible."""
    user_id = _user_id(config)
    if not user_id:
        return "Error: User ID not found in context."

    async with async_session_maker() as db:
        result = await db.execute(
            select(Order).filter(Order.id == order_id, Order.user_id == user_id)
        )
        order = result.scalars().first()
        if not order:
            return f"Order {order_id} not found."

        if order.days_since_delivery and order.days_since_delivery <= 30:
            order.status = "refunded"
            await db.commit()
            return f"Refund processed successfully for order {order_id}."
        return f"Order {order_id} is not eligible for refund (past 30 days limit)."


@tool
async def search_faq(query: str) -> str:
    """Search the FAQ and policy documents for answers."""
    return await retrieve_faq(query)


@tool
async def recall_memory(
    limit: int = 10,
    *,
    config: Annotated[RunnableConfig, InjectedToolArg()],
) -> str:
    """Recall the last N messages from the user's past conversations."""
    user_id = _user_id(config)
    if not user_id:
        return "Error: User ID not found in context."

    async with async_session_maker() as db:
        result = await db.execute(
            select(Conversation)
            .filter(Conversation.user_id == user_id)
            .order_by(Conversation.created_at.desc())
        )
        convo = result.scalars().first()
        if not convo:
            return "No past conversations found."

        result_messages = await db.execute(
            select(DBMessage)
            .filter(DBMessage.conversation_id == convo.id)
            .order_by(DBMessage.created_at.desc())
            .limit(limit)
        )
        messages = result_messages.scalars().all()
        if not messages:
            return "No messages found in recent conversation."

        messages.reverse()
        return "\n".join([f"{m.role}: {m.content}" for m in messages])


@tool
async def escalate_to_human(
    reason: str,
    config: Annotated[RunnableConfig, InjectedToolArg()],
) -> str:
    """Escalate the issue to a human agent."""
    conversation_id = _conversation_id(config)
    if not conversation_id:
        return "Error: Conversation ID not found in context."

    async with async_session_maker() as db:
        escalation = Escalation(conversation_id=conversation_id, reason=reason)
        db.add(escalation)
        await db.commit()
        return "Issue escalated successfully. A human agent will respond shortly."


tools = [get_order_status, process_refund, search_faq, recall_memory, escalate_to_human]
