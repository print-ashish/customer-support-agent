from typing import Annotated
import datetime

from langchain_core.tools import tool, InjectedToolArg
from langchain_core.runnables import RunnableConfig
from sqlalchemy import select

from db.models import Order, Escalation
from db.session import async_session_maker
from rag.retriever import search_faq as search_faq_async


def _user_id(config: RunnableConfig) -> int | None:
    return config.get("configurable", {}).get("user_id")


def _conversation_id(config: RunnableConfig) -> int | None:
    return config.get("configurable", {}).get("conversation_id")


def get_days_since_delivery(order: Order) -> int | None:
    """Calculate days since delivery date or fall back to legacy column."""
    if order.delivered_at:
        delivered = order.delivered_at
        if delivered.tzinfo is None:
            # naive datetime
            now = datetime.datetime.now()
        else:
            # timezone-aware datetime
            now = datetime.datetime.now(datetime.timezone.utc)
        delta = now - delivered
        return max(0, delta.days)
    return order.days_since_delivery


def check_refund_eligibility_internal(order: Order) -> tuple[bool, str]:
    """Internal helper to verify if an order is eligible for refund."""
    if order.status == "refunded":
        return False, f"Order #{order.id} has already been refunded."
    if order.status == "cancelled":
        return False, f"Order #{order.id} cannot be refunded because it is cancelled."
    if order.status in ("processing", "shipped"):
        return False, f"Order #{order.id} is currently '{order.status}' and cannot be refunded. Refunds are only allowed for delivered orders."
    if order.status != "delivered":
        return False, f"Order #{order.id} is in status '{order.status}' and is not eligible for a refund."

    category = (order.item_category or "").lower()
    if category in ("perishable", "perishables"):
        return False, f"Order #{order.id} contains a perishable item ({order.item_name}) which is non-refundable per our policy."
    if category in ("personalized", "custom", "customized"):
        return False, f"Order #{order.id} contains a personalized/custom item ({order.item_name}) which is non-refundable per our policy."

    days = get_days_since_delivery(order)
    if days is None:
        return False, f"Could not determine delivery date for order #{order.id}."
    if days > 30:
        return False, f"Order #{order.id} was delivered {days} days ago, which exceeds our 30-day refund window."

    return True, f"Order #{order.id} ({order.item_name}) is eligible for a full refund of ${order.amount:.2f}."


@tool
async def list_my_orders(
    config: Annotated[RunnableConfig, InjectedToolArg()],
) -> str:
    """List all orders belonging to the logged-in user."""
    user_id = _user_id(config)
    if not user_id:
        return "Error: User ID not found in context."

    async with async_session_maker() as db:
        result = await db.execute(
            select(Order)
            .filter(Order.user_id == user_id)
            .order_by(Order.created_at.desc())
        )
        orders = result.scalars().all()
        if not orders:
            return "You do not have any orders."

        lines = ["Here are your orders:"]
        for o in orders:
            info = f"- **Order #{o.id}**: {o.item_name} | Status: **{o.status}** | Price: ${o.amount:.2f}"
            if o.status == "shipped" and o.tracking_number:
                info += f" | Tracking Number: {o.tracking_number}"
            elif o.status == "delivered":
                days = get_days_since_delivery(o)
                if days is not None:
                    info += f" (Delivered {days} days ago)"
            elif o.status == "cancelled" and o.cancellation_reason:
                info += f" (Reason: {o.cancellation_reason})"
            lines.append(info)

        return "\n".join(lines)


@tool
async def get_order_status(
    order_id: int,
    config: Annotated[RunnableConfig, InjectedToolArg()],
) -> str:
    """Check the status of a specific order and provide rich lifecycle/action hints."""
    print("checking for order", order_id)
    user_id = _user_id(config)
    if not user_id:
        return "Error: User ID not found in context."

    async with async_session_maker() as db:
        result = await db.execute(
            select(Order).filter(Order.id == order_id, Order.user_id == user_id)
        )
        order = result.scalars().first()
        if not order:
            return f"Order #{order_id} not found or doesn't belong to this user."

        status_desc = f"Order #{order_id} status: **{order.status}**."
        
        if order.status == "processing":
            return status_desc + " (Hint: This order is still processing. It is eligible for cancellation.)"
        elif order.status == "shipped":
            tracking = f" (Tracking: {order.tracking_number})" if order.tracking_number else ""
            return status_desc + f"{tracking} (Hint: This order has been shipped. It can still be cancelled, but you may need to refuse delivery or return it once it arrives.)"
        elif order.status == "delivered":
            days = get_days_since_delivery(order)
            days_str = f" delivered {days} days ago" if days is not None else ""
            eligible, reason = check_refund_eligibility_internal(order)
            hint = " It is eligible for a refund." if eligible else f" However, it is not eligible for refund because: {reason}"
            return status_desc + f" (Delivered{days_str}.{hint})"
        elif order.status == "cancelled":
            reason_str = f" Reason: '{order.cancellation_reason}'." if order.cancellation_reason else ""
            return status_desc + f" (Cancelled.{reason_str})"
        elif order.status == "refunded":
            return status_desc + " (Refunded. No further actions can be taken on this order.)"
        
        return status_desc


@tool
async def cancel_order(
    order_id: int = None,
    reason: str = None,
    config: Annotated[RunnableConfig, InjectedToolArg()] = None,
) -> str:
    """Cancel an order that is processing or shipped."""
    if order_id is None:
        return "Error: You must provide an order_id to cancel an order. Please look up the user's orders first or ask the user for the order ID."
    if not reason:
        return "Error: You must provide a cancellation reason. Please ask the user why they want to cancel the order first."

    user_id = _user_id(config)
    if not user_id:
        return "Error: User ID not found in context."

    async with async_session_maker() as db:
        result = await db.execute(
            select(Order).filter(Order.id == order_id, Order.user_id == user_id)
        )
        order = result.scalars().first()
        if not order:
            return f"Order #{order_id} not found."

        if order.status == "cancelled":
            return f"Order #{order_id} is already cancelled."
        if order.status == "refunded":
            return f"Order #{order_id} cannot be cancelled because it has already been refunded."
        if order.status == "delivered":
            return f"Order #{order_id} has already been delivered. It cannot be cancelled. You can request a refund instead."

        if order.status not in ("processing", "shipped"):
            return f"Order #{order_id} with status '{order.status}' cannot be cancelled."

        # Cancel it
        old_status = order.status
        order.status = "cancelled"
        order.cancellation_reason = reason
        
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc) if (order.created_at and order.created_at.tzinfo) else datetime.datetime.now()
        order.cancelled_at = now
        
        await db.commit()

        if old_status == "shipped":
            return (
                f"Order #{order_id} was successfully cancelled (reason: {reason}). "
                f"Note: Since the order was already shipped, it has left our warehouse. "
                f"Please refuse the package at the time of delivery or return it using our free return label once it arrives."
            )
        return f"Order #{order_id} was successfully cancelled (reason: {reason})."


@tool
async def check_refund_eligibility(
    order_id: int = None,
    config: Annotated[RunnableConfig, InjectedToolArg()] = None,
) -> str:
    """Check if an order is eligible for a refund, without executing it."""
    if order_id is None:
        return "Error: You must provide an order_id to check refund eligibility. Please look up the user's orders first or ask the user for the order ID."

    user_id = _user_id(config)
    if not user_id:
        return "Error: User ID not found in context."

    async with async_session_maker() as db:
        result = await db.execute(
            select(Order).filter(Order.id == order_id, Order.user_id == user_id)
        )
        order = result.scalars().first()
        if not order:
            return f"Order #{order_id} not found."

        eligible, reason = check_refund_eligibility_internal(order)
        return reason


@tool
async def process_refund(
    order_id: int = None,
    config: Annotated[RunnableConfig, InjectedToolArg()] = None,
) -> str:
    """Process a refund for a given order if eligible."""
    if order_id is None:
        return "Error: You must provide an order_id to process a refund. Please look up the user's orders first or ask the user for the order ID."

    user_id = _user_id(config)
    if not user_id:
        return "Error: User ID not found in context."

    async with async_session_maker() as db:
        result = await db.execute(
            select(Order).filter(Order.id == order_id, Order.user_id == user_id)
        )
        order = result.scalars().first()
        if not order:
            return f"Order #{order_id} not found."

        eligible, reason = check_refund_eligibility_internal(order)
        if not eligible:
            return f"Refund blocked: {reason}"

        # If eligible, process it!
        order.status = "refunded"
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc) if (order.created_at and order.created_at.tzinfo) else datetime.datetime.now()
        order.refunded_at = now
        await db.commit()
        return (
            f"Refund of ${order.amount:.2f} processed successfully for order #{order_id}. "
            f"The amount has been credited to the original payment method and will appear in 5-7 business days."
        )


@tool
async def search_faq(query: str) -> str:
    """Search the FAQ and policy documents for answers."""
    return await search_faq_async(query)


@tool
async def escalate_to_human(
    reason: str,
    category: str = "general",
    config: Annotated[RunnableConfig, InjectedToolArg()] = None,
) -> str:
    """Escalate the issue to a human agent with a category ('billing_dispute', 'damaged_item', 'policy_exception', 'fraud', 'general')."""
    conversation_id = _conversation_id(config)
    if not conversation_id:
        return "Error: Conversation ID not found in context."

    user_id = _user_id(config)

    allowed_categories = ["billing_dispute", "damaged_item", "policy_exception", "fraud", "general"]
    cat = category.lower() if category else "general"
    if cat not in allowed_categories:
        cat = "general"

    async with async_session_maker() as db:
        db.add(Escalation(conversation_id=conversation_id, user_id=user_id, reason=reason, category=cat))
        await db.commit()
        return f"Issue escalated successfully under category '{cat}'. A human agent will respond shortly."


tools = [
    list_my_orders,
    get_order_status,
    cancel_order,
    check_refund_eligibility,
    process_refund,
    search_faq,
    escalate_to_human,
]
