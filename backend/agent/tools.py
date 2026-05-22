from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from rag.retriever import search_faq as retrieve_faq
from db.session import SessionLocal
from db.models import Order, Escalation, Message as DBMessage, Conversation

@tool
def get_order_status(order_id: int, config: RunnableConfig) -> str:
    """Check the status of a specific order."""
    user_id = config.get("configurable", {}).get("user_id")
    if not user_id:
        return "Error: User ID not found in context."
        
    db = SessionLocal()
    try:
        order = db.query(Order).filter(Order.id == order_id, Order.user_id == user_id).first()
        if not order:
            return f"Order {order_id} not found or doesn't belong to this user."
        
        # Simple eligibility check
        eligible = "yes" if order.days_since_delivery and order.days_since_delivery <= 30 else "no"
        return f"Order {order_id} status: {order.status}. Eligible for refund: {eligible}."
    finally:
        db.close()

@tool
def process_refund(order_id: int, config: RunnableConfig) -> str:
    """Process a refund for a given order if eligible."""
    user_id = config.get("configurable", {}).get("user_id")
    if not user_id:
        return "Error: User ID not found in context."
        
    db = SessionLocal()
    try:
        order = db.query(Order).filter(Order.id == order_id, Order.user_id == user_id).first()
        if not order:
            return f"Order {order_id} not found."
        
        if order.days_since_delivery and order.days_since_delivery <= 30:
            order.status = "refunded"
            db.commit()
            return f"Refund processed successfully for order {order_id}."
        else:
            return f"Order {order_id} is not eligible for refund (past 30 days limit)."
    finally:
        db.close()

@tool
def search_faq(query: str) -> str:
    """Search the FAQ and policy documents for answers."""
    print('searching for the query , ' , query)
    rag_response = retrieve_faq(query)
    print('rag response , ' , rag_response)
    return rag_response

@tool
def recall_memory(config: RunnableConfig, limit: int = 10) -> str:
    """Recall the last N messages from the user's past conversations."""
    user_id = config.get("configurable", {}).get("user_id")
    if not user_id:
        return "Error: User ID not found in context."
        
    db = SessionLocal()
    try:
        # Fetch latest conversation for user
        convo = db.query(Conversation).filter(Conversation.user_id == user_id).order_by(Conversation.created_at.desc()).first()
        if not convo:
            return "No past conversations found."
        
        messages = db.query(DBMessage).filter(DBMessage.conversation_id == convo.id).order_by(DBMessage.created_at.desc()).limit(limit).all()
        if not messages:
            return "No messages found in recent conversation."
        
        # Reverse to chronological order
        messages.reverse()
        formatted = "\n".join([f"{m.role}: {m.content}" for m in messages])
        return formatted
    finally:
        db.close()

@tool
def escalate_to_human(reason: str, config: RunnableConfig) -> str:
    """Escalate the issue to a human agent."""
    conversation_id = config.get("configurable", {}).get("conversation_id")
    if not conversation_id:
        return "Error: Conversation ID not found in context."
        
    db = SessionLocal()
    try:
        print("adding to the escalation", conversation_id, reason)
        escalation = Escalation(conversation_id=conversation_id, reason=reason)
        db.add(escalation)
        db.commit()
        return "Issue escalated successfully. A human agent will respond shortly."
    finally:
        db.close()

# List of tools to pass to the agent
tools = [get_order_status, process_refund, search_faq, recall_memory, escalate_to_human]
