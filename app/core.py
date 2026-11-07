from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import JSON, DateTime, Numeric, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    database_url: str = 'postgresql+psycopg://precos:precos@localhost:5433/precos'
    upload_dir: str = './inbox'
    api_title: str = 'PreçosAPI'


settings = Settings()
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = 'sources'
    id: Mapped[UUID] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True)
    name: Mapped[str] = mapped_column(Text)
    publisher: Mapped[str] = mapped_column(Text)


class Release(Base):
    __tablename__ = 'releases'
    id: Mapped[UUID] = mapped_column(primary_key=True)
    source_id: Mapped[UUID] = mapped_column()
    reference_month: Mapped[datetime] = mapped_column()
    region_code: Mapped[str | None] = mapped_column(String(8))
    title: Mapped[str | None] = mapped_column(Text)
    source_file_name: Mapped[str] = mapped_column(Text)
    source_sha256: Mapped[str] = mapped_column(String(64))
    release_metadata: Mapped[dict[str, Any]] = mapped_column('metadata', JSON)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Item(Base):
    __tablename__ = 'items'
    id: Mapped[UUID] = mapped_column(primary_key=True)
    source_id: Mapped[UUID] = mapped_column()
    code: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String(32))
    category: Mapped[str | None] = mapped_column(Text)


class ItemPrice(Base):
    __tablename__ = 'item_prices'
    id: Mapped[UUID] = mapped_column(primary_key=True)
    item_id: Mapped[UUID] = mapped_column()
    release_id: Mapped[UUID] = mapped_column()
    region_code: Mapped[str | None] = mapped_column(String(8))
    pricing_variant: Mapped[str] = mapped_column(String(32))
    price: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    price_origin: Mapped[str | None] = mapped_column(Text)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSON)
