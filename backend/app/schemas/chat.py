from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------- provider status ----------


class ProvidersStatus(BaseModel):
    chain: List[str]
    available: List[str]


# ---------- send message ----------


class ChatSendRequest(BaseModel):
    """Send one user turn. Server persists it, calls the LLM with history."""

    conversation_id: Optional[str] = Field(
        default=None, description="Existing conversation id; omit to start a new one"
    )
    content: str = Field(min_length=1, max_length=8000)
    provider: Optional[str] = Field(
        default=None, description="Preferred provider: nvidia | openrouter | groq | gemini"
    )
    max_tokens: Optional[int] = Field(default=None, ge=1, le=8000)
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)


class ChatSendResponse(BaseModel):
    conversation_id: str
    user_message_id: str
    assistant_message_id: str
    text: str
    risk_level: str
    provider: Optional[str] = None
    model: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None


# ---------- read ----------


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    role: Literal["user", "assistant", "system"]
    content: str
    provider: Optional[str] = None
    model: Optional[str] = None
    risk_level: Optional[str] = None
    created_at: datetime


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: Optional[str]
    archived: bool
    created_at: datetime
    updated_at: datetime


class ConversationWithMessages(ConversationRead):
    messages: List[MessageRead] = []


class ConversationUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)
    archived: Optional[bool] = None


# ---------- legacy stateless ----------


class ChatMessageIn(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class ChatRequest(BaseModel):
    """Stateless request kept for /chat/stream and internal callers."""

    messages: List[ChatMessageIn] = Field(min_length=1, max_length=64)
    provider: Optional[str] = None
    max_tokens: Optional[int] = Field(default=None, ge=1, le=8000)
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)


class ChatResponse(BaseModel):
    text: str
    provider: str
    model: str
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
