from datetime import date, time

from pydantic import BaseModel, Field


class NamePayload(BaseModel):
    surname: str = Field(max_length=100)
    given: str = Field(max_length=100)
    patronymic: str | None = Field(default=None, max_length=100)


class OnboardRequest(BaseModel):
    telegram_id: int
    name: str = Field(max_length=100)  # форма обращения (салютация)
    birth_date: date
    birth_time: time | None = None
    birth_time_precision: str = "unknown"
    birth_city: str = Field(max_length=200)
    birth_lat: float
    birth_lon: float
    timezone: str
    sex: str = Field(pattern="^[mf]$")  # F04: пол обязателен (да-юнь Ба-Цзы)
    name_birth: NamePayload  # F04: ФИО при рождении (контур имени нумерологии)
    name_current: NamePayload | None = None  # §3.5: дельта «при рождении → сейчас»
    place_id: str | None = None  # F02: реестр спорных поясов
    region: str | None = None
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


class GeoResult(BaseModel):
    name: str
    lat: float
    lon: float
    timezone: str


class InterpretationBlock(BaseModel):
    planet: str
    planet_ru: str
    sign: str
    sign_ru: str
    symbol: str
    house: int | None = None
    degree: float
    text: str


class PortraitResponse(BaseModel):
    blocks: list[InterpretationBlock]
    portrait: str
