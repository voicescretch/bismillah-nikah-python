from datetime import datetime
from typing import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base, relationship

from bot.config import DATABASE_URL

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


# Buat async engine dengan connection pool yang cocok untuk serverless
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=5,
    max_overflow=10,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Context manager untuk async session SQLAlchemy."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db():
    """Inisialisasi tabel database."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
