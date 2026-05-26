from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, JSON, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from .session import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    orders = relationship("Order", back_populates="user")
    conversations = relationship("Conversation", back_populates="user")

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    item_name = Column(String, nullable=True)                           # e.g. "Wireless Headphones"
    item_category = Column(String, nullable=True)                       # electronics / perishable / personalized / clothing / etc.
    status = Column(String, default="processing")                       # processing / shipped / delivered / cancelled / refunded
    amount = Column(Float, nullable=False)
    tracking_number = Column(String, nullable=True)                     # set when status = shipped
    days_since_delivery = Column(Integer, nullable=True)                # legacy / seed data fallback
    delivered_at = Column(DateTime(timezone=True), nullable=True)       # actual delivery timestamp
    cancellation_reason = Column(String, nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    refunded_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="orders")


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_id = Column(String, unique=True, index=True, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    escalation = relationship("Escalation", back_populates="conversation", uselist=False)

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    role = Column(String, nullable=False) # 'user', 'agent', 'system', 'tool'
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    conversation = relationship("Conversation", back_populates="messages")

class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(768)) # 768 dimensions for nomic-embed-text or typical embeddings, can adjust
    metadata_ = Column("metadata", JSON, nullable=True) # avoiding reserved keyword conflicts if any, though metadata is usually ok
    source = Column(String, nullable=True)

class Escalation(Base):
    __tablename__ = "escalations"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reason = Column(Text, nullable=False)
    category = Column(String, default="general", nullable=True)
    status = Column(String, default="open") # 'open', 'resolved'
    human_response = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    conversation = relationship("Conversation", back_populates="escalation")
    user = relationship("User")
