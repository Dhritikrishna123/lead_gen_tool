"""
Pydantic schemas for request / response validation.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


# ---------------------------------------------------------------------------
# Job
# ---------------------------------------------------------------------------
class JobCreate(BaseModel):
    prompt: str = Field(..., description="Natural language prompt describing target leads")
    lead_count: int = Field(default=100, ge=1, le=1000)


class JobResponse(BaseModel):
    id: int
    prompt: str
    lead_count: int
    status: str
    progress: int
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result_url: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Lead
# ---------------------------------------------------------------------------
class LeadResponse(BaseModel):
    id: int
    name: Optional[str] = None
    email: Optional[str] = None
    company: Optional[str] = None
    title: Optional[str] = None
    source_url: Optional[str] = None
    description: Optional[str] = None
    confidence: float

    model_config = ConfigDict(from_attributes=True)
