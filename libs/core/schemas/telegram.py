from __future__ import annotations

from pydantic import BaseModel, Field


class TgUser(BaseModel):
    id: int
    is_bot: bool | None = None
    first_name: str | None = None
    username: str | None = None


class TgChat(BaseModel):
    id: int
    type: str
    title: str | None = None


class TgMessage(BaseModel):
    message_id: int
    from_: TgUser | None = Field(default=None, alias="from")
    chat: TgChat
    text: str | None = None


class TelegramUpdate(BaseModel):
    update_id: int
    message: TgMessage | None = None
