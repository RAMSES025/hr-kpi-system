from pydantic import BaseModel, ConfigDict
from datetime import date, datetime
from typing import Optional
from models import RoleEnum, AbsenceTypeEnum, RequestStatusEnum

class UserCreate(BaseModel):
    full_name: str
    email: str
    password: str
    role: RoleEnum = RoleEnum.EMPLOYEE
    position: Optional[str] = None
    base_salary: float = 0.0
    max_bonus: float = 0.0

class UserResponse(BaseModel):
    id: int
    full_name: str
    email: str
    role: RoleEnum
    position: Optional[str]
    vacation_balance: int

    model_config = ConfigDict(from_attributes=True)

class AbsenceCreate(BaseModel):
    absence_type: AbsenceTypeEnum
    start_date: date
    end_date: date
    reason: Optional[str] = None

class AbsenceResponse(BaseModel):
    id: int
    user_id: int
    absence_type: AbsenceTypeEnum
    start_date: date
    end_date: date
    status: RequestStatusEnum
    reason: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class TimeLogResponse(BaseModel):
    id: int
    user_id: int
    work_date: date
    clock_in: Optional[datetime]
    clock_out: Optional[datetime]
    is_late: int

    model_config = ConfigDict(from_attributes=True)
