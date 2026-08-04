import hashlib
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from lunora.api.schemas import (
    AskRequest,
    AskResponse,
    ChartResponse,
    GeoResult,
    OnboardRequest,
    OnboardResponse,
    PortraitResponse,
)
from lunora.calc.geocode import geocode_city
from lunora.calc.timezone import timezone_for
from lunora.interpret.portrait import (
    PORTRAIT_SYSTEM_PROMPT,
    build_interpretation_blocks,
    build_portrait_prompt,
)
from lunora.calc.engine import calculate
from lunora.calc.serialize import chart_to_dict
from lunora.calc.types import BirthData, BirthTimePrecision
from lunora.db import async_session
from lunora.llm.client import generate_response
from lunora.models.chart import CalculationRun, NatalChart
from lunora.models.thread import Message, Thread
from lunora.models.user import User

router = APIRouter(prefix="/api")


@router.post("/onboard", response_model=OnboardResponse)
async def onboard(req: OnboardRequest):
    async with async_session() as session:
        existing = await session.execute(
            select(User).where(User.telegram_id == req.telegram_id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(400, "User already exists")

        user = User(
            telegram_id=req.telegram_id,
            name=req.name,
            birth_date=req.birth_date,
            birth_time=req.birth_time,
            birth_time_precision=req.birth_time_precision.lower(),
            birth_city=req.birth_city,
            birth_lat=req.birth_lat,
            birth_lon=req.birth_lon,
            timezone=req.timezone,
            referral_code=secrets.token_urlsafe(12),
            consent_given_at=datetime.utcnow(),
        )
        session.add(user)
        await session.flush()

        birth = BirthData(
            birth_date=req.birth_date,
            birth_time=req.birth_time,
            precision=BirthTimePrecision(req.birth_time_precision),
            lat=req.birth_lat,
            lon=req.birth_lon,
            timezone=req.timezone,
            name=req.name,
        )
        full = calculate(birth)

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

        input_str = f"{req.birth_date}|{req.birth_time}|{req.birth_lat}|{req.birth_lon}"
        run = CalculationRun(
            chart_id=chart.id,
            engine_version="0.1.0",
            zodiac_type="tropical+sidereal",
            ayanamsa="lahiri",
            house_system="placidus",
            input_hash=hashlib.sha256(input_str.encode()).hexdigest(),
        )
        session.add(run)
        await session.commit()

        return OnboardResponse(
            user_id=str(user.id),
            chart={"western": w, "vedic": v, "chinese": c, "numerology": n},
        )


@router.get("/chart/{user_id}", response_model=ChartResponse)
async def get_chart(user_id: uuid.UUID):
    async with async_session() as session:
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
async def ask(req: AskRequest):
    user_id = uuid.UUID(req.user_id)

    async with async_session() as session:
        chart_row = await session.execute(
            select(NatalChart)
            .where(NatalChart.user_id == user_id)
            .order_by(NatalChart.created_at.desc())
            .limit(1)
        )
        chart = chart_row.scalar_one_or_none()
        if not chart:
            raise HTTPException(404, "Chart not found, onboard first")

        user_row = await session.execute(
            select(User).where(User.id == user_id)
        )
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
        history = [
            {"role": m.role, "content": m.content}
            for m in msg_rows.scalars().all()
        ]

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
async def get_portrait(user_id: uuid.UUID):
    async with async_session() as session:
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
            return PortraitResponse(blocks=[], portrait="Недостаточно данных для построения портрета.")

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
