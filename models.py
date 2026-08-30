import enum
from sqlalchemy import Column, Integer, String, Float, DateTime, Date, ForeignKey, Enum, Text
from sqlalchemy.orm import relationship
from datetime import datetime

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

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(Enum(RoleEnum), default=RoleEnum.EMPLOYEE)

    # Должность сотрудника (например: "специалист", "старший консультант").
    # Используется, чтобы группировать сотрудников в календаре отсутствий,
    # как на прототипе с рабочего стола. Необязательное поле.
    position = Column(String, nullable=True, default=None)

    base_salary = Column(Float, default=0.0)    
    max_bonus = Column(Float, default=0.0)      
    vacation_balance = Column(Integer, default=28) 
    
    time_logs = relationship("TimeLog", back_populates="user", cascade="all, delete-orphan")
    absences = relationship("AbsenceRequest", back_populates="user", cascade="all, delete-orphan")
    penalties = relationship("KPIPenalty", back_populates="user", cascade="all, delete-orphan")

class TimeLog(Base):
    __tablename__ = "time_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    work_date = Column(Date, nullable=False) 
    clock_in = Column(DateTime, nullable=True)  
    clock_out = Column(DateTime, nullable=True) 
    is_late = Column(Integer, default=0) 
    
    user = relationship("User", back_populates="time_logs")

class AbsenceRequest(Base):
    __tablename__ = "absence_requests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    absence_type = Column(Enum(AbsenceTypeEnum), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    
    status = Column(Enum(RequestStatusEnum), default=RequestStatusEnum.PENDING)
    reason = Column(Text, nullable=True) 
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="absences")

class KPIPenalty(Base):
    __tablename__ = "kpi_penalties"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    target_month = Column(Date, nullable=False) 
    reason = Column(String, nullable=False) 
    penalty_percent = Column(Float, nullable=False) 
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="penalties")
