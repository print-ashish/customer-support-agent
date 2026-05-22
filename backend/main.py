from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
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

from sqlalchemy import text

# Setup pgvector extension if not exists
with engine.connect() as conn:
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    conn.commit()

# Create tables if they don't exist
# We execute this here for quick setup without alembic in dev mode
models.Base.metadata.create_all(bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(title="AI Customer Support Agent", lifespan=lifespan)

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

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
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

    user = db.query(models.User).filter(models.User.email == email).first()

    if user is None:
        raise credentials_exception

    return user
@app.post("/auth/register", response_model=UserResponse)
def register(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = get_password_hash(user.password)
    new_user = models.User(email=user.email, password_hash=hashed_password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@app.post("/auth/login", response_model=Token)
def login(form_data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form_data.email).first()
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

from langchain_core.messages import HumanMessage, AIMessage
from agent.graph import agent_app
from memory.store import get_latest_conversation, create_conversation, save_message, get_conversation_history
from langfuse.langchain import CallbackHandler

langfuse_handler = CallbackHandler()

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str
    escalated: bool = False

@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    convo = get_latest_conversation(db, user.id)
    if not convo:
        convo = create_conversation(db, user.id)
        
    save_message(db, convo.id, "user", request.message)
    
    config = {
        "configurable": {
            "thread_id": str(convo.id),
            "user_id": user.id,
            "conversation_id": convo.id
        },
        "callbacks": [langfuse_handler]
    }
    input_state = {
        "messages": [HumanMessage(content=request.message)],
        "user_id": user.id,
    }
    
    final_state = agent_app.invoke(input_state, config=config)
    messages = final_state.get("messages", [])
    last_message = messages[-1]
    print("last message == ", last_message)
    
    response_text = last_message.content if hasattr(last_message, 'content') else str(last_message)
    save_message(db, convo.id, "agent", response_text)
    
    # Check if escalation occurred
    escalated = False
    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
         if any(call.get("name") == "escalate_to_human" for call in last_message.tool_calls):
             escalated = True
             response_text = "I've escalated your issue to a human agent. They will review it shortly."
    
    return {"response": response_text, "escalated": escalated}

@app.get("/chat/history")
def chat_history(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    convo = get_latest_conversation(db, user.id)
    if not convo:
        return []
    return get_conversation_history(db, convo.id)

@app.get("/admin/dashboard")
def admin_dashboard(db: Session = Depends(get_db)):
    # Very basic auth normally, skipped for simplicity
    escalations = db.query(models.Escalation).filter(models.Escalation.status == "open").all()
    return escalations

class AdminResponse(BaseModel):
    escalation_id: int
    response: str

@app.post("/admin/escalations")
def admin_respond(req: AdminResponse, db: Session = Depends(get_db)):
    escalation = db.query(models.Escalation).filter(models.Escalation.id == req.escalation_id).first()
    if not escalation:
        raise HTTPException(status_code=404, detail="Escalation not found")
    
    escalation.human_response = req.response
    escalation.status = "resolved"
    
    save_message(db, escalation.conversation_id, "human_agent", req.response)
    db.commit()
    return {"status": "success"}
