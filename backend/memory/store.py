from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.models import Conversation, Message as DBMessage

async def create_conversation(db: AsyncSession, user_id: int):
    convo = Conversation(user_id=user_id)
    db.add(convo)
    await db.commit()
    await db.refresh(convo)
    return convo

async def get_latest_conversation(db: AsyncSession, user_id: int):
    result = await db.execute(
        select(Conversation)
        .filter(Conversation.user_id == user_id)
        .order_by(Conversation.created_at.desc())
    )
    return result.scalars().first()

async def save_message(db: AsyncSession, conversation_id: int, role: str, content: str):
    msg = DBMessage(conversation_id=conversation_id, role=role, content=content)
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return msg

async def get_conversation_history(db: AsyncSession, conversation_id: int):
    result = await db.execute(
        select(DBMessage)
        .filter(DBMessage.conversation_id == conversation_id)
        .order_by(DBMessage.created_at.asc())
    )
    messages = result.scalars().all()
    return [{"role": m.role, "content": m.content} for m in messages]
