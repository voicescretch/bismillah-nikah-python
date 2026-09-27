import logging
import ssl
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base, relationship

from bot.config import DATABASE_URL

logger = logging.getLogger(__name__)

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    telegram_id = Column(BigInteger, primary_key=True, index=True)
    username = Column(String(255), nullable=True)
    full_name = Column(String(255), nullable=False)
    group_id = Column(Integer, ForeignKey("savings_groups.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    group = relationship("SavingsGroup", back_populates="members")
    transactions = relationship("Transaction", back_populates="user")


class SavingsGroup(Base):
    __tablename__ = "savings_groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    invite_code = Column(String(6), unique=True, nullable=True, index=True)
    code_expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    members = relationship("User", back_populates="group")
    transactions = relationship("Transaction", back_populates="group")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False)
    group_id = Column(Integer, ForeignKey("savings_groups.id", ondelete="CASCADE"), nullable=False)
    type = Column(String(20), nullable=False)  # 'PEMASUKAN' atau 'PENGELUARAN'
    amount = Column(BigInteger, nullable=False)
    description = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="transactions")
    group = relationship("SavingsGroup", back_populates="transactions")


# Engine & Session Maker singleton
_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker] = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is not None:
        return _engine

    if not DATABASE_URL:
        raise ValueError("DATABASE_URL belum diatur di Environment Variables!")

    connect_args = {}
    # Jika koneksi ke cloud (Neon, Supabase, dll) yang membutuhkan SSL
    if "localhost" not in DATABASE_URL and "127.0.0.1" not in DATABASE_URL:
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        connect_args["ssl"] = ssl_ctx

    _engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args=connect_args,
    )
    return _engine


def get_session_factory() -> async_sessionmaker:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Context manager untuk async session SQLAlchemy."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db():
    """Inisialisasi tabel database."""
    if not DATABASE_URL:
        logger.warning("DATABASE_URL kosong, lewati inisialisasi tabel database.")
        return
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
