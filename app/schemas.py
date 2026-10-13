from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

Stage = Literal["lead", "qualified", "proposal", "negotiation", "won", "lost"]
ActivityType = Literal["call", "email", "meeting", "task"]


def _blank_to_none(v):
    if isinstance(v, str) and not v.strip():
        return None
    return v


class Ref(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class CompanyIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    industry: str | None = None
    city: str | None = None
    website: str | None = None

    _blank = field_validator("industry", "city", "website", mode="before")(_blank_to_none)


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    industry: str | None
    city: str | None
    website: str | None
    created_at: datetime
    contact_count: int = 0
    open_deal_value: Decimal = Decimal(0)


class ContactIn(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    phone: str | None = None
    title: str | None = None
    company_id: int | None = None

    _blank = field_validator("phone", "title", "company_id", mode="before")(_blank_to_none)


class ContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    first_name: str
    last_name: str
    email: str
    phone: str | None
    title: str | None
    company: Ref | None
    created_at: datetime


class DealIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    value: Decimal = Field(ge=0)
    stage: Stage = "lead"
    expected_close: date | None = None
    company_id: int | None = None
    contact_id: int | None = None

    _blank = field_validator("expected_close", "company_id", "contact_id", mode="before")(
        _blank_to_none
    )


class DealOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    value: Decimal
    stage: Stage
    expected_close: date | None
    company: Ref | None
    contact: Ref | None
    created_at: datetime


class StageUpdate(BaseModel):
    stage: Stage


class ActivityIn(BaseModel):
    type: ActivityType
    subject: str = Field(min_length=1, max_length=200)
    notes: str | None = None
    due_date: date | None = None
    contact_id: int | None = None
    deal_id: int | None = None

    _blank = field_validator("notes", "due_date", "contact_id", "deal_id", mode="before")(
        _blank_to_none
    )


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    type: ActivityType
    subject: str
    notes: str | None
    due_date: date | None
    done: bool
    contact: Ref | None
    deal: Ref | None
    created_at: datetime


class StageSummary(BaseModel):
    stage: Stage
    count: int
    value: Decimal


class Dashboard(BaseModel):
    open_pipeline_value: Decimal
    open_deal_count: int
    won_value_last_90_days: Decimal
    win_rate: float
    contact_count: int
    company_count: int
    overdue_activity_count: int
    stages: list[StageSummary]
    closing_soon: list[DealOut]
    upcoming_activities: list[ActivityOut]
