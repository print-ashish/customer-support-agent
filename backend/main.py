from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from pydantic import BaseModel
from contextlib import asynccontextmanager
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from db.session import engine, get_db
from db import models
from auth.jwt import get_password_hash, verify_password, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
from datetime import timedelta
from auth.jwt import jwt, JWTError, SECRET_KEY, ALGORITHM

import os
from dotenv import load_dotenv

load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(models.Base.metadata.create_all)

    yield

app = FastAPI(title="AI Customer Support Agent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()


# Pydantic Schemas
class UserCreate(BaseModel):
    email: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class UserResponse(BaseModel):
    id: int
    email: str

    class Config:
        from_attributes = True

class LoginRequest(BaseModel):
    email: str
    password: str

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    result = await db.execute(select(models.User).filter(models.User.email == email))
    user = result.scalars().first()

    if user is None:
        raise credentials_exception

    return user

@app.post("/auth/register", response_model=UserResponse)
async def register(user: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.User).filter(models.User.email == user.email))
    db_user = result.scalars().first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_password = get_password_hash(user.password)
    new_user = models.User(email=user.email, password_hash=hashed_password)
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user

@app.post("/auth/login", response_model=Token)
async def login(form_data: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.User).filter(models.User.email == form_data.email))
    user = result.scalars().first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email, "id": user.id}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/")
def read_root():
    return {"message": "Welcome to AI Customer Support Agent API"}

import asyncio
from langchain_core.messages import HumanMessage, AIMessage
from agent.graph import get_agent_app
from memory.store import get_latest_conversation, create_conversation, save_message, get_conversation_history
# from langfuse.langchain import CallbackHandler
from langfuse.langchain import CallbackHandler


langfuse_handler = CallbackHandler()

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str
    escalated: bool = False


def _final_agent_reply(messages) -> str:
    """Last assistant message with text (skip tool-call-only turns)."""
    for msg in reversed(messages):
        if not isinstance(msg, AIMessage) or msg.tool_calls:
            continue
        content = msg.content
        if isinstance(content, str) and content.strip():
            return content
        if isinstance(content, list):
            text = "".join(
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            ).strip()
            if text:
                return text
    last = messages[-1]
    return last.content if hasattr(last, "content") and last.content else str(last)


from langfuse import Langfuse, propagate_attributes
from langfuse.langchain import CallbackHandler

langfuse = Langfuse(
    public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
    secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
    host=os.getenv("LANGFUSE_HOST"),
)

@app.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user)
):

    convo = await get_latest_conversation(db, user.id)

    if not convo:
        convo = await create_conversation(db, user.id)

    await save_message(db, convo.id, "user", request.message)

    handler = CallbackHandler()

    config = {
        "configurable": {
            "thread_id": str(convo.id),
            "user_id": user.id,
            "conversation_id": convo.id
        },
        "callbacks": [handler],
    }

    input_state = {
        "messages": [HumanMessage(content=request.message)],
        "user_id": user.id,
    }

    with propagate_attributes(
        session_id=f"conversation-{convo.id}",
        user_id=str(user.id),
    ):

        final_state = await get_agent_app().ainvoke(
            input_state,
            config=config
        )

    messages = final_state.get("messages", [])
    response_text = _final_agent_reply(messages)

    await save_message(db, convo.id, "agent", response_text)

    langfuse.flush()

    return {
        "response": response_text,
        "escalated": False
    }

# @app.post("/chat", response_model=ChatResponse)
# async def chat(
#     request: ChatRequest,
#     db: AsyncSession = Depends(get_db),
#     user: models.User = Depends(get_current_user)
# ):
#     convo = await get_latest_conversation(db, user.id)

#     if not convo:
#         convo = await create_conversation(db, user.id)

#     await save_message(db, convo.id, "user", request.message)

#     langfuse_handler = CallbackHandler(
#         secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
#         public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
#         host=os.getenv("LANGFUSE_HOST"),
#         session_id=f"conversation-{convo.id}",
#         user_id=str(user.id),
#     )

#     config = {
#         "configurable": {
#             "thread_id": str(convo.id),
#             "user_id": user.id,
#             "conversation_id": convo.id,
#         },
#         "callbacks": [langfuse_handler],
#         "metadata": {
#             "conversation_id": str(convo.id),
#             "user_email": user.email,
#         }
#     }

#     input_state = {
#         "messages": [HumanMessage(content=request.message)],
#         "user_id": user.id,
#     }

#     final_state = await get_agent_app().ainvoke(
#         input_state,
#         config=config
#     )

#     messages = final_state.get("messages", [])
#     response_text = _final_agent_reply(messages)

#     await save_message(db, convo.id, "agent", response_text)

#     return {
#         "response": response_text,
#         "escalated": False
#     }

# @app.post("/chat", response_model=ChatResponse)
# async def chat(request: ChatRequest, db: AsyncSession = Depends(get_db), user: models.User = Depends(get_current_user)):
#     convo = await get_latest_conversation(db, user.id)
#     if not convo:
#         convo = await create_conversation(db, user.id)

#     await save_message(db, convo.id, "user", request.message)

#     config = {
#         "configurable": {
#             "thread_id": str(convo.id),
#             "user_id": user.id,
#             "conversation_id": convo.id
#         },
#         # "callbacks": [langfuse_handler]
#         "callbacks": [langfuse_handler]
#     }
#     input_state = {
#         "messages": [HumanMessage(content=request.message)],
#         "user_id": user.id,
#     }

#     final_state = await get_agent_app().ainvoke(input_state, config=config)

#     messages = final_state.get("messages", [])
#     response_text = _final_agent_reply(messages)
#     await save_message(db, convo.id, "agent", response_text)

#     escalated = False
#     for msg in messages:
#         if isinstance(msg, AIMessage) and msg.tool_calls:
#             if any(call.get("name") == "escalate_to_human" for call in msg.tool_calls):
#                 escalated = True
#                 response_text = "I've escalated your issue to a human agent. They will review it shortly."
#                 break

#     return {"response": response_text, "escalated": escalated}

@app.get("/chat/history")
async def chat_history(db: AsyncSession = Depends(get_db), user: models.User = Depends(get_current_user)):
    convo = await get_latest_conversation(db, user.id)
    if not convo:
        return []
    return await get_conversation_history(db, convo.id)

@app.get("/admin/dashboard")
async def admin_dashboard(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.Escalation).filter(models.Escalation.status == "open"))
    escalations = result.scalars().all()
    return escalations

class AdminResponse(BaseModel):
    escalation_id: int
    response: str

@app.post("/admin/escalations")
async def admin_respond(req: AdminResponse, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.Escalation).filter(models.Escalation.id == req.escalation_id))
    escalation = result.scalars().first()
    if not escalation:
        raise HTTPException(status_code=404, detail="Escalation not found")

    escalation.human_response = req.response
    escalation.status = "resolved"

    await save_message(db, escalation.conversation_id, "human_agent", req.response)
    await db.commit()
    return {"status": "success"}
