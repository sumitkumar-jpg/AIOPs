"""Pydantic request/response schemas for the API."""

from typing import List, Optional

from pydantic import BaseModel


class InjectRequest(BaseModel):
    scenario_id: str
    missing_sources: List[str] = []
    stale_sources: List[str] = []


class NoteRequest(BaseModel):
    note: Optional[str] = None
