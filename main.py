from fastapi import FastAPI, Depends, HTTPException, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import List

from datetime import datetime, date

import models
import schemas
from database import SessionLocal, engine

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Corporate HR & KPI System")
templates = Jinja2Templates(directory="templates")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/")
def read_root():
    return {"message": "Бэкенд HR-системы работает!"}


@app.post("/users/", response_model=schemas.UserResponse, tags=["Сотрудники"])
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Сотрудник с таким email уже существует")
    
    new_user = models.User(
        full_name=user.full_name,
        email=user.email,
        hashed_password=user.password,
        role=user.role,
        base_salary=user.base_salary,
        max_bonus=user.max_bonus
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@app.get("/users/", response_model=List[schemas.UserResponse], tags=["Сотрудники"])
def get_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    # Получаем список всех сотрудников
    users = db.query(models.User).offset(skip).limit(limit).all()
    return users

@app.post("/users/{user_id}/absences/", response_model=schemas.AbsenceResponse, tags=["Отсутствия"])
def create_absence_request(user_id: int, absence: schemas.AbsenceCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")

    new_absence = models.AbsenceRequest(
        user_id=user_id,
        absence_type=absence.absence_type,
        start_date=absence.start_date,
        end_date=absence.end_date,
        reason=absence.reason
    )
    db.add(new_absence)
    db.commit()
    db.refresh(new_absence)
    return new_absence

## --- ЭНДПОИНТЫ ДЛЯ УЧЕТА ВРЕМЕНИ ---

@app.post("/users/{user_id}/clock-in/", response_model=schemas.TimeLogResponse, tags=["Учет времени"])
def clock_in(user_id: int, db: Session = Depends(get_db)):
    # 1. Проверяем, существует ли сотрудник
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")

    today = date.today()
    now = datetime.now()
    
    # 2. Проверяем, не отмечался ли он уже сегодня
    existing_log = db.query(models.TimeLog).filter(
        models.TimeLog.user_id == user_id,
        models.TimeLog.work_date == today
    ).first()

    if existing_log is not None and existing_log.clock_in is not None:
        raise HTTPException(status_code=400, detail="Вы уже начали рабочий день сегодня")

    # 3. Считаем опоздание. Допустим, рабочий день начинается строго в 09:00.
    expected_start = now.replace(hour=9, minute=0, second=0, microsecond=0)
    late_minutes = 0
    
    if now > expected_start:
        late_minutes = int((now - expected_start).total_seconds() / 60)

    # 4. Создаем запись в базе
    new_log = models.TimeLog(
        user_id=user_id,
        work_date=today,
        clock_in=now,
        is_late=late_minutes
    )
    
    db.add(new_log)
    db.commit()
    db.refresh(new_log)
    
    return new_log

# --- WEB-ИНТЕРФЕЙС ---

@app.get("/dashboard/{user_id}", tags=["Web интерфейс"])
def user_dashboard(user_id: int, request: Request, db: Session = Depends(get_db)):
    # Находим самого сотрудника
    user = db.query(models.User).filter(models.User.id == user_id).first()
    
    # Запрашиваем историю заявок ТОЛЬКО этого конкретного сотрудника
    user_requests = db.query(models.AbsenceRequest).filter(models.AbsenceRequest.user_id == user_id).all()
    
    return templates.TemplateResponse(
        request=request, 
        name="dashboard.html", 
        context={
            "request": request, 
            "user": user, 
            "user_requests": user_requests  # Передаем историю в шаблон
        }
    )

# --- АДМИН-ПАНЕЛЬ (WEB-ИНТЕРФЕЙС) ---

@app.get("/admin", tags=["Web интерфейс"])
def admin_dashboard(
    request: Request,
    error: str = None,
    err_user: int = None,
    err_needed: int = None,
    err_available: int = None,
    db: Session = Depends(get_db)
):
    users = db.query(models.User).all()
    pending_requests = db.query(models.AbsenceRequest).filter(models.AbsenceRequest.status == "PENDING").all()
    history_requests = db.query(models.AbsenceRequest).filter(
        models.AbsenceRequest.status != "PENDING"
    ).order_by(models.AbsenceRequest.id.desc()).all()

    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "request": request,
            "users": users,
            "pending_requests": pending_requests,
            "history_requests": history_requests,
            "error": error,
            "err_user": err_user,
            "err_needed": err_needed,
            "err_available": err_available,
        }
    )

@app.post("/admin/add-user", tags=["Web интерфейс"])
def add_user_from_web(
    # В отличие от JSON (Pydantic), данные из HTML-формы нужно принимать через Form(...)
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    base_salary: float = Form(0.0),
    max_bonus: float = Form(0.0),
    db: Session = Depends(get_db)
):
    # Проверяем, свободен ли email
    db_user = db.query(models.User).filter(models.User.email == email).first()
    if db_user:
        # В идеале тут нужно возвращать страницу с ошибкой, но пока упростим
        raise HTTPException(status_code=400, detail="Сотрудник с таким email уже существует")
    
    # Создаем нового пользователя
    new_user = models.User(
        full_name=full_name,
        email=email,
        hashed_password=password,
        role=models.RoleEnum.EMPLOYEE, # По умолчанию делаем обычным сотрудником
        base_salary=base_salary,
        max_bonus=max_bonus
    )
    
    db.add(new_user)
    db.commit()
    
    # После успешного добавления, перенаправляем пользователя обратно на страницу админки
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/web/clock-in/{user_id}", tags=["Web интерфейс"])
def clock_in_from_web(user_id: int, db: Session = Depends(get_db)):
    from datetime import date, datetime
    
    today = date.today()
    now = datetime.now()
    
    # 1. Проверяем, не нажимал ли сотрудник кнопку сегодня
    existing_log = db.query(models.TimeLog).filter(
        models.TimeLog.user_id == user_id,
        models.TimeLog.work_date == today
    ).first()

    # 2. Если записей за сегодня нет, создаем новую
    if existing_log is None:
        # Считаем опоздание (допустим, рабочий день начинается строго в 09:00)
        expected_start = now.replace(hour=9, minute=0, second=0, microsecond=0)
        late_minutes = 0
        
        if now > expected_start:
            late_minutes = int((now - expected_start).total_seconds() / 60)

        # Записываем в базу
        new_log = models.TimeLog(
            user_id=user_id,
            work_date=today,
            clock_in=now,
            is_late=late_minutes
        )
        db.add(new_log)
        db.commit()
        
    # 3. Перезагружаем страницу личного кабинета
    return RedirectResponse(url=f"/dashboard/{user_id}", status_code=303)

@app.post("/web/request-absence/{user_id}", tags=["Web интерфейс"])
def request_absence_web(
    user_id: int, 
    start_date: str = Form(...), 
    end_date: str = Form(...), 
    reason: str = Form(...), 
    db: Session = Depends(get_db)
):
    from datetime import datetime
    from fastapi.responses import RedirectResponse
    
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    if end < start:
        start, end = end, start
    
    # Словарь-переводчик: переводим русский текст из формы в системный Enum базы данных
    type_mapping = {
        "Оплачиваемый отпуск": "VACATION",
        "Больничный": "SICK_LEAVE",
        "Отгул": "DAY_OFF"
    }
    
    # Получаем правильный системный ключ (по умолчанию ставим VACATION, если что-то пойдет не так)
    db_absence_type = type_mapping.get(reason, "VACATION")
    
    new_request = models.AbsenceRequest(
        user_id=user_id,
        absence_type=db_absence_type,  # <-- Передаем системный тип (например, VACATION)
        start_date=start,
        end_date=end,
        reason=reason,                 # <-- А здесь оставляем русский текст для интерфейса
        status="PENDING"
    )
    
    db.add(new_request)
    db.commit()
    
    return RedirectResponse(url=f"/dashboard/{user_id}", status_code=303)

@app.post("/web/approve-absence/{request_id}", tags=["Web интерфейс"])
def approve_absence(request_id: int, db: Session = Depends(get_db)):
    from fastapi.responses import RedirectResponse

    req = db.query(models.AbsenceRequest).filter(models.AbsenceRequest.id == request_id).first()
    if not req:
        return RedirectResponse(url="/admin", status_code=303)

    # Если это оплачиваемый отпуск — сначала проверяем, хватает ли дней
    if "VACATION" in str(req.absence_type):
        days_count = (req.end_date - req.start_date).days + 1
        user = db.query(models.User).filter(models.User.id == req.user_id).first()

        if user and user.vacation_balance < days_count:
            # Дней не хватает — НЕ одобряем, возвращаемся с флагом ошибки
            return RedirectResponse(
                url=f"/admin?error=insufficient_balance&err_user={req.user_id}&err_needed={days_count}&err_available={user.vacation_balance}",
                status_code=303
            )

        # Дней хватает — списываем
        db.query(models.User).filter(models.User.id == req.user_id).update(
            {"vacation_balance": models.User.vacation_balance - days_count}
        )

    db.query(models.AbsenceRequest).filter(models.AbsenceRequest.id == request_id).update({"status": "APPROVED"})
    db.commit()

    return RedirectResponse(url="/admin", status_code=303)


@app.post("/web/reject-absence/{request_id}", tags=["Web интерфейс"])
def reject_absence(request_id: int, db: Session = Depends(get_db)):
    from fastapi.responses import RedirectResponse

    req = db.query(models.AbsenceRequest).filter(models.AbsenceRequest.id == request_id).first()
    if req:
        was_approved = "APPROVED" in str(req.status)

        db.query(models.AbsenceRequest).filter(models.AbsenceRequest.id == request_id).update({"status": "REJECTED"})

        # Если заявку до этого уже одобрили и это отпуск — возвращаем списанные дни
        if was_approved and "VACATION" in str(req.absence_type):
            days_count = (req.end_date - req.start_date).days + 1
            db.query(models.User).filter(models.User.id == req.user_id).update(
                {"vacation_balance": models.User.vacation_balance + days_count}
            )
        db.commit()

    return RedirectResponse(url="/admin", status_code=303)

@app.post("/web/delete-absence/{request_id}", tags=["Web интерфейс"])
def delete_absence(request_id: int, db: Session = Depends(get_db)):
    from fastapi.responses import RedirectResponse
    req = db.query(models.AbsenceRequest).filter(models.AbsenceRequest.id == request_id).first()
    
    if req:
        user_id = req.user_id
        # Бронебойная проверка статуса (учитывает и текст, и Enum базы данных)
        if "PENDING" in str(req.status):
            db.delete(req)
            db.commit()
        return RedirectResponse(url=f"/dashboard/{user_id}", status_code=303)
        
    return RedirectResponse(url="/admin", status_code=303)


@app.post("/web/edit-absence/{request_id}", tags=["Web интерфейс"])
def edit_absence(
    request_id: int, 
    start_date: str = Form(...), 
    end_date: str = Form(...), 
    reason: str = Form(...), 
    db: Session = Depends(get_db)
):
    from datetime import datetime
    from fastapi.responses import RedirectResponse
    
    req = db.query(models.AbsenceRequest).filter(models.AbsenceRequest.id == request_id).first()
    
    if req and "PENDING" in str(req.status):
        # Конвертируем данные
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
        if end < start:
            start, end = end, start
        
        type_mapping = {
            "Оплачиваемый отпуск": "VACATION",
            "Больничный": "SICK_LEAVE",
            "Отгул": "DAY_OFF"
        }
        db_absence_type = type_mapping.get(reason, "VACATION")
        
        # Обновляем базу данных правильным методом, чтобы Pylance не выдавал ошибок
        db.query(models.AbsenceRequest).filter(models.AbsenceRequest.id == request_id).update({
            "start_date": start,
            "end_date": end,
            "reason": reason,
            "absence_type": db_absence_type
        })
        db.commit()
        
        return RedirectResponse(url=f"/dashboard/{req.user_id}", status_code=303)
        
    return RedirectResponse(url="/admin", status_code=303)