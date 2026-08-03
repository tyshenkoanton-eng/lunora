from datetime import date, time

from pydantic import BaseModel, Field


class OnboardRequest(BaseModel):
    telegram_id: int
    name: str = Field(max_length=100)
    birth_date: date
    birth_time: time | None = None
    birth_time_precision: str = "unknown"
    birth_city: str = Field(max_length=200)
    birth_lat: float
    birth_lon: float
    timezone: str
    init_data: str


class OnboardResponse(BaseModel):
    user_id: str
    chart: dict


class AskRequest(BaseModel):
    user_id: str
    thread_id: str | None = None
    question: str = Field(max_length=2000)


class AskResponse(BaseModel):
    thread_id: str
    answer: str
    category: str


class ChartResponse(BaseModel):
    western: dict
    vedic: dict
    chinese: dict
    numerology: dict
    summary: dict
