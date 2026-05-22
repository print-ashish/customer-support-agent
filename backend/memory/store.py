from sqlalchemy.orm import Session
from db.models import Conversation, Message as DBMessage

def create_conversation(db: Session, user_id: int):
    convo = Conversation(user_id=user_id)
    db.add(convo)
    db.commit()
    db.refresh(convo)
    return convo

def get_latest_conversation(db: Session, user_id: int):
    return db.query(Conversation).filter(Conversation.user_id == user_id).order_by(Conversation.created_at.desc()).first()

def save_message(db: Session, conversation_id: int, role: str, content: str):
    msg = DBMessage(conversation_id=conversation_id, role=role, content=content)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg

def get_conversation_history(db: Session, conversation_id: int):
    messages = db.query(DBMessage).filter(DBMessage.conversation_id == conversation_id).order_by(DBMessage.created_at.asc()).all()
    return [{"role": m.role, "content": m.content} for m in messages]
