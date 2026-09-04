import enum
from typing import List, Optional
from datetime import datetime, date
from sqlalchemy import Integer, String, Float, DateTime, Date, ForeignKey, Enum, Text
from sqlalchemy.orm import relationship, Mapped, mapped_column

# Импортируем Base из соседнего файла
from database import Base

# --- ПЕРЕЧИСЛЕНИЯ (Статусы и Роли) ---

class RoleEnum(enum.Enum):
    EMPLOYEE = "employee"
    HR = "hr"
    MANAGER = "manager"
    ADMIN = "admin"

class AbsenceTypeEnum(enum.Enum):
    VACATION = "vacation"
    SICK_LEAVE = "sick_leave"
    DAY_OFF = "day_off"

class RequestStatusEnum(enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

# --- ТАБЛИЦЫ ---

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    full_name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[RoleEnum] = mapped_column(Enum(RoleEnum), default=RoleEnum.EMPLOYEE)

    # Должность сотрудника (например: "специалист", "старший консультант").
    # Используется, чтобы группировать сотрудников в календаре отсутствий,
    # как на прототипе с рабочего стола. Необязательное поле.
    position: Mapped[Optional[str]] = mapped_column(String, nullable=True, default=None)

    base_salary: Mapped[float] = mapped_column(Float, default=0.0)
    max_bonus: Mapped[float] = mapped_column(Float, default=0.0)
    vacation_balance: Mapped[int] = mapped_column(Integer, default=28)

    time_logs: Mapped[List["TimeLog"]] = relationship("TimeLog", back_populates="user", cascade="all, delete-orphan")
    absences: Mapped[List["AbsenceRequest"]] = relationship("AbsenceRequest", back_populates="user", cascade="all, delete-orphan")
    penalties: Mapped[List["KPIPenalty"]] = relationship("KPIPenalty", back_populates="user", cascade="all, delete-orphan")

class TimeLog(Base):
    __tablename__ = "time_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)

    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    clock_in: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    clock_out: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_late: Mapped[int] = mapped_column(Integer, default=0)

    user: Mapped["User"] = relationship("User", back_populates="time_logs")

class AbsenceRequest(Base):
    __tablename__ = "absence_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)

    absence_type: Mapped[AbsenceTypeEnum] = mapped_column(Enum(AbsenceTypeEnum), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)

    status: Mapped[RequestStatusEnum] = mapped_column(Enum(RequestStatusEnum), default=RequestStatusEnum.PENDING)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="absences")

class KPIPenalty(Base):
    __tablename__ = "kpi_penalties"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)

    target_month: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    penalty_percent: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="penalties")
