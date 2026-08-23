from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class LocationCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    building: str | None = Field(None, max_length=120)
    description: str | None = None


class LocationResponse(ORMModel):
    id: int
    name: str
    building: str | None
    description: str | None


class LocationListResponse(BaseModel):
    total: int
    results: list[LocationResponse]


class CategoryResponse(ORMModel):
    id: int
    name: str


class CategoryCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)


class CategoryListResponse(BaseModel):
    total: int
    results: list[CategoryResponse]
