"""전체 스키마 (설계 문서 §4.4). 원본 명세 §5를 못 찾아 컬럼은 SP1 스펙 기준으로 정의했다."""
from __future__ import annotations

import uuid
from datetime import date, datetime, time

from geoalchemy2 import Geography
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _now():
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class Poi(Base):
    __tablename__ = "poi"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(32), index=True)  # attraction/culture/food/shopping/...
    content_type_id: Mapped[int] = mapped_column(SmallInteger)  # TourAPI 12,14,15,28,32,38,39
    address: Mapped[str | None] = mapped_column(String(300))
    geom = mapped_column(Geography("POINT", srid=4326))
    phone: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(String(500))
    popularity: Mapped[float] = mapped_column(Float, default=0.0)
    hours_text: Mapped[str | None] = mapped_column(Text)  # 원문 (usetime + restdate)
    hours_confidence: Mapped[float | None] = mapped_column(Float)  # NULL = 아직 파싱 안 됨
    embedding = mapped_column(Vector(768))
    area_code: Mapped[int | None] = mapped_column(SmallInteger)
    sigungu_code: Mapped[int | None] = mapped_column(SmallInteger)
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    sources: Mapped[list[PoiSource]] = relationship(back_populates="poi")


class PoiSource(Base):
    __tablename__ = "poi_source"
    __table_args__ = (UniqueConstraint("source", "source_poi_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    poi_id: Mapped[int] = mapped_column(ForeignKey("poi.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(32))  # 'tourapi'
    source_poi_id: Mapped[str] = mapped_column(String(64))
    raw: Mapped[dict] = mapped_column(JSONB)
    fetched_at: Mapped[datetime] = _now()

    poi: Mapped[Poi] = relationship(back_populates="sources")


class PoiHours(Base):
    """요일별 영업시간. 요일당 여러 구간(점심 휴게 등)이면 행이 여러 개."""

    __tablename__ = "poi_hours"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    poi_id: Mapped[int] = mapped_column(ForeignKey("poi.id", ondelete="CASCADE"), index=True)
    weekday: Mapped[int] = mapped_column(SmallInteger)  # 0=월 … 6=일
    open_time: Mapped[time | None] = mapped_column(Time)
    close_time: Mapped[time | None] = mapped_column(Time)  # 자정 넘김은 24:00 → 00:00 + next_day
    next_day: Mapped[bool] = mapped_column(Boolean, default=False)
    last_order_time: Mapped[time | None] = mapped_column(Time)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)


class PoiClosure(Base):
    __tablename__ = "poi_closures"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    poi_id: Mapped[int] = mapped_column(ForeignKey("poi.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(24))  # public_holiday / nth_weekday / date_range / date
    rule: Mapped[dict] = mapped_column(JSONB)  # 예: {"nth": 2, "weekday": 0}
    note: Mapped[str | None] = mapped_column(Text)


class TravelTimeCache(Base):
    __tablename__ = "travel_time_cache"
    __table_args__ = (UniqueConstraint("from_poi_id", "to_poi_id", "mode"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    from_poi_id: Mapped[int] = mapped_column(ForeignKey("poi.id", ondelete="CASCADE"))
    to_poi_id: Mapped[int] = mapped_column(ForeignKey("poi.id", ondelete="CASCADE"))
    mode: Mapped[str] = mapped_column(String(8))  # car / foot / transit
    minutes: Mapped[float] = mapped_column(Float)
    distance_m: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(16))  # osrm / odsay
    fetched_at: Mapped[datetime] = _now()
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AppUser(Base):
    __tablename__ = "app_user"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kakao_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    nickname: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = _now()


class AnonSession(Base):
    __tablename__ = "anon_session"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = _now()


class Itinerary(Base):
    __tablename__ = "itinerary"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"), index=True)
    anon_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("anon_session.id"), index=True)
    share_token: Mapped[str | None] = mapped_column(String(32), unique=True)
    title: Mapped[str | None] = mapped_column(String(200))
    conditions: Mapped[dict] = mapped_column(JSONB)  # 조건 JSON (lodging 포함)
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    items: Mapped[list[ItineraryItem]] = relationship(
        back_populates="itinerary", order_by="ItineraryItem.day, ItineraryItem.seq"
    )


class ItineraryItem(Base):
    __tablename__ = "itinerary_item"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    itinerary_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("itinerary.id", ondelete="CASCADE"), index=True
    )
    poi_id: Mapped[int] = mapped_column(ForeignKey("poi.id"))
    day: Mapped[int] = mapped_column(SmallInteger)
    seq: Mapped[int] = mapped_column(SmallInteger)
    start_time: Mapped[time | None] = mapped_column(Time)
    end_time: Mapped[time | None] = mapped_column(Time)
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    travel_mode: Mapped[str | None] = mapped_column(String(8))  # 이전 장소에서 여기까지
    travel_minutes: Mapped[float | None] = mapped_column(Float)
    travel_estimated: Mapped[bool] = mapped_column(Boolean, default=False)

    itinerary: Mapped[Itinerary] = relationship(back_populates="items")


class FeedbackLog(Base):
    __tablename__ = "feedback_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    anon_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("anon_session.id"))
    itinerary_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("itinerary.id"))
    poi_id: Mapped[int | None] = mapped_column(ForeignKey("poi.id"))
    action: Mapped[str] = mapped_column(String(24))  # recommended/removed/added/reordered/locked/...
    payload: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _now()


class PoiReport(Base):
    __tablename__ = "poi_report"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    poi_id: Mapped[int] = mapped_column(ForeignKey("poi.id"), index=True)
    anon_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("anon_session.id"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    type: Mapped[str] = mapped_column(String(16))  # closed / hours_wrong / other
    message: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="open")
    created_at: Mapped[datetime] = _now()


class Holiday(Base):
    __tablename__ = "holiday"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))


class StayDefault(Base):
    __tablename__ = "stay_default"

    category: Mapped[str] = mapped_column(String(32), primary_key=True)
    minutes: Mapped[int] = mapped_column(SmallInteger)
