from __future__ import annotations

from pydantic import BaseModel, Field


class AuthConfigResponse(BaseModel):
    is_configured: bool
    client_id: str = ""
    allowed_domains: list[str] = Field(default_factory=list)


class GoogleCredentialRequest(BaseModel):
    credential: str


class AuthSessionResponse(BaseModel):
    is_authenticated: bool
    email: str | None = None
    name: str | None = None
    picture: str | None = None
