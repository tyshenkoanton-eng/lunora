import hashlib
import hmac
import secrets
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from lunora.api.auth import require_telegram_id
from lunora.api.schemas import (
    AskRequest,
    AskResponse,
    ChartResponse,
    GeoResult,
    OnboardRequest,
    OnboardResponse,
    PortraitResponse,
)
from lunora.calc.engine import calculate, provenance, resolve_moment
from lunora.calc.geocode import geocode_city
from lunora.calc.serialize import chart_to_dict
from lunora.calc.timezone import timezone_for
from lunora.calc.types import BirthData
from lunora.calc.types import BirthTimePrecision as CalcPrecision
from lunora.config import settings
from lunora.db import async_session
from lunora.engines.numerology import FullName, NumerologyInputError
from lunora.engines.numerology import normalize as normalize_name
from lunora.interpret.portrait import (
    PORTRAIT_SYSTEM_PROMPT,
    build_interpretation_blocks,
    build_portrait_prompt,
)
from lunora.llm.client import generate_response
from lunora.models.chart import CalculationRun, NatalChart
from lunora.models.thread import Message, Thread
from lunora.models.user import BirthTimePrecision, User

router = APIRouter(prefix="/api")

# F04/F09/В-1: движок нумерологии кириллический. Отказ онбординга по ФИО должен нести
# человекочитаемое предупреждение, привязанное к полю ввода, а не только машинный код.
_NAME_FIELD_RU = {
    "surname": "фамилия",
    "given": "имя",
    "patronymic": "отчество",
}


def _name_reject_detail(exc: "NumerologyInputError") -> dict:
    field_ru = _NAME_FIELD_RU.get(exc.field or "", "ФИО")
    base = "Введите ФИО кириллицей, как в русскоязычном документе."
    if exc.code == "latin_not_supported":
        message = f"Поле «{field_ru}» заполнено латиницей. {base}"
    elif exc.code == "mixed_script":
        message = (
            f"В поле «{field_ru}» смешаны кириллица и латиница. {base}"
        )
    elif exc.code in ("unsupported_letter", "invalid_character"):
        message = (
            f"В поле «{field_ru}» есть символ, который движок не принимает. {base}"
        )
    elif exc.code == "empty_name_part":
        message = f"Заполните поле «{field_ru}»."
    else:
        message = base
    return {
        "error": "name_rejected",
        "code": exc.code,
        "field": exc.field,
        "message": message,
    }


async def _authorized_user(session, telegram_id: int, requested_user_id) -> User:
    """Владелец = telegram_id из подписанной initData. user_id из пути/тела должен совпасть,
    иначе 403 (IDOR-защита). Несуществующий telegram_id → 404; чужой user_id → 403, без
    различения «нет карты»/«чужая карта» наружу."""
    row = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = row.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    if str(user.id) != str(requested_user_id):
        raise HTTPException(
            403,
            {"error": "forbidden", "code": "not_owner", "message": "доступ только к своей карте"},
        )
    return user


@router.post("/onboard", response_model=OnboardResponse)
async def onboard(req: OnboardRequest, telegram_id: int = Depends(require_telegram_id)):
    # Владелец берётся из подписанной initData, а не из тела: telegram_id в теле — только сверка.
    if req.telegram_id != telegram_id:
        raise HTTPException(
            403,
            {"error": "forbidden", "code": "telegram_id_mismatch",
             "message": "telegram_id в запросе не совпадает с подписью"},
        )
    async with async_session() as session:
        existing = await session.execute(select(User).where(User.telegram_id == telegram_id))
        if existing.scalar_one_or_none():
            raise HTTPException(400, "User already exists")

        user = User(
            telegram_id=telegram_id,
            name=req.name,
            birth_date=req.birth_date,
            birth_time=req.birth_time,
            birth_time_precision=BirthTimePrecision(req.birth_time_precision.lower()),
            birth_city=req.birth_city,
            birth_lat=req.birth_lat,
            birth_lon=req.birth_lon,
            timezone=req.timezone,
            place_id=req.place_id,
            region=req.region,
            sex=req.sex,
            name_surname=req.name_birth.surname,
            name_given=req.name_birth.given,
            name_patronymic=req.name_birth.patronymic,
            referral_code=secrets.token_urlsafe(12),
            consent_given_at=datetime.utcnow(),
        )
        session.add(user)
        await session.flush()

        birth = BirthData(
            birth_date=req.birth_date,
            birth_time=req.birth_time,
            precision=CalcPrecision(req.birth_time_precision.lower()),
            lat=req.birth_lat,
            lon=req.birth_lon,
            timezone=req.timezone,
            sex=req.sex,
            full_name=FullName(req.name_birth.surname, req.name_birth.given,
                               req.name_birth.patronymic),
            name=req.name,
            name_current=(
                FullName(req.name_current.surname, req.name_current.given,
                         req.name_current.patronymic)
                if req.name_current else None
            ),
            place_id=req.place_id,
            region=req.region,
        )
        # F04/F09 (В-1): ФИО латиницей/смешанным алфавитом на онбординге — отказ 422, карта
        # не сохраняется (§1.3). Движок вне API (пересчёты) считает контур имени not_computed.
        try:
            normalize_name(birth.full_name)
            if birth.name_current is not None:
                normalize_name(birth.name_current)
        except NumerologyInputError as exc:
            raise HTTPException(422, _name_reject_detail(exc)) from exc

        moment = resolve_moment(birth)
        full = calculate(birth, moment)

        w = chart_to_dict(full.western)
        v = chart_to_dict(full.vedic)
        c = chart_to_dict(full.chinese)
        n = chart_to_dict(full.numerology)

        chart = NatalChart(
            user_id=user.id,
            western=w,
            vedic=v,
            chinese=c,
            numerology=n,
            summary={},
        )
        session.add(chart)
        await session.flush()

        prov = provenance(birth, moment)
        input_str = (
            f"{req.birth_date}|{req.birth_time}|{req.birth_lat}|{req.birth_lon}|"
            f"{req.timezone}|{req.birth_time_precision}|{req.place_id}|{req.sex}"
        )
        # F07/ARCHITECTURE §3.2: HMAC с серверным перцем, а не голый SHA-256 входа
        input_hash = hmac.new(
            settings.calc_server_pepper.encode(), input_str.encode(), hashlib.sha256
        ).hexdigest()
        run = CalculationRun(
            chart_id=chart.id,
            engine_version="0.1.0",
            zodiac_type="tropical+sidereal",
            ayanamsa="lahiri",
            house_system="placidus",
            input_hash=input_hash,
            timezone=req.timezone,
            precision=req.birth_time_precision.lower(),
            tolerance_minutes=birth.tolerance_minutes,
            place_id=req.place_id,
            region=req.region,
            dispute_id=prov.get("dispute_id"),
            provenance=prov,
        )
        session.add(run)
        await session.commit()

        return OnboardResponse(
            user_id=str(user.id),
            chart={"western": w, "vedic": v, "chinese": c, "numerology": n},
        )


@router.get("/chart/{user_id}", response_model=ChartResponse)
async def get_chart(user_id: uuid.UUID, telegram_id: int = Depends(require_telegram_id)):
    async with async_session() as session:
        await _authorized_user(session, telegram_id, user_id)
        result = await session.execute(
            select(NatalChart)
            .where(NatalChart.user_id == user_id)
            .order_by(NatalChart.created_at.desc())
            .limit(1)
        )
        chart = result.scalar_one_or_none()
        if not chart:
            raise HTTPException(404, "Chart not found")

        return ChartResponse(
            western=chart.western,
            vedic=chart.vedic,
            chinese=chart.chinese,
            numerology=chart.numerology,
            summary=chart.summary,
        )


@router.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest, telegram_id: int = Depends(require_telegram_id)):
    user_id = uuid.UUID(req.user_id)

    async with async_session() as session:
        await _authorized_user(session, telegram_id, user_id)
        chart_row = await session.execute(
            select(NatalChart)
            .where(NatalChart.user_id == user_id)
            .order_by(NatalChart.created_at.desc())
            .limit(1)
        )
        chart = chart_row.scalar_one_or_none()
        if not chart:
            raise HTTPException(404, "Chart not found, onboard first")

        user_row = await session.execute(select(User).where(User.id == user_id))
        user = user_row.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "User not found")

        if req.thread_id:
            thread_id = uuid.UUID(req.thread_id)
            thread_row = await session.execute(
                select(Thread).where(Thread.id == thread_id, Thread.user_id == user_id)
            )
            thread = thread_row.scalar_one_or_none()
            if not thread:
                raise HTTPException(404, "Thread not found")
        else:
            thread = Thread(user_id=user_id, title=req.question[:100])
            session.add(thread)
            await session.flush()

        msg_rows = await session.execute(
            select(Message)
            .where(Message.thread_id == thread.id)
            .order_by(Message.created_at.asc())
            .limit(20)
        )
        history = [{"role": m.role, "content": m.content} for m in msg_rows.scalars().all()]

        chart_data = {
            "western": chart.western,
            "vedic": chart.vedic,
            "chinese": chart.chinese,
            "numerology": chart.numerology,
        }

        answer, category = await generate_response(
            question=req.question,
            chart_data=chart_data,
            precision=user.birth_time_precision.value,
            history=history,
        )

        session.add(Message(thread_id=thread.id, role="user", content=req.question))
        session.add(Message(thread_id=thread.id, role="assistant", content=answer))
        thread.message_count += 2
        await session.commit()

        return AskResponse(
            thread_id=str(thread.id),
            answer=answer,
            category=category.value,
        )


@router.get("/portrait/{user_id}", response_model=PortraitResponse)
async def get_portrait(user_id: uuid.UUID, telegram_id: int = Depends(require_telegram_id)):
    async with async_session() as session:
        await _authorized_user(session, telegram_id, user_id)
        chart_row = await session.execute(
            select(NatalChart)
            .where(NatalChart.user_id == user_id)
            .order_by(NatalChart.created_at.desc())
            .limit(1)
        )
        chart = chart_row.scalar_one_or_none()
        if not chart:
            raise HTTPException(404, "Chart not found")

        chart_data = {
            "western": chart.western,
            "vedic": chart.vedic,
            "chinese": chart.chinese,
            "numerology": chart.numerology,
        }
        blocks = build_interpretation_blocks(chart_data)

        if not blocks:
            return PortraitResponse(
                blocks=[], portrait="Недостаточно данных для построения портрета."
            )

        prompt = build_portrait_prompt(blocks, chart_data)
        from lunora.llm.client import _call_llm

        messages = [
            {"role": "system", "content": PORTRAIT_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        portrait = await _call_llm(messages)
        return PortraitResponse(blocks=blocks, portrait=portrait)


@router.get("/geocode", response_model=list[GeoResult])
async def geocode(q: str = Query(min_length=2, max_length=200)):
    results = await geocode_city(q)
    out = []
    for r in results:
        tz = timezone_for(r["lat"], r["lon"])
        if tz:
            out.append(GeoResult(name=r["name"], lat=r["lat"], lon=r["lon"], timezone=tz))
    return out
