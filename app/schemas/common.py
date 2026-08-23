from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class MessageResponse(BaseModel):
    """Generic acknowledgement body. Typed so no route returns a raw dict."""

    detail: str = Field(..., examples=["Item deleted."])


class HealthResponse(BaseModel):
    status: str = Field(..., examples=["ok"])
    database: str = Field(..., examples=["reachable"])
    version: str = Field(..., examples=["1.0.0"])
