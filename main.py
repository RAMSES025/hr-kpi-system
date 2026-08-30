from fastapi import FastAPI, Depends, HTTPException, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional, cast

from datetime import datetime, date, timedelta
import calendar as calendar_module

import models
import schemas
from database import SessionLocal, engine

models.Base.metadata.create_all(bind=engine)


def ensure_column(table: str, column: str, coltype: str):
    """
    Лёгкая "самодельная" миграция без Alembic.
    Если в старой базе данных ещё нет новой колонки (например, 'position'),
    добавляем её через ALTER TABLE, ничего не удаляя и не ломая.
    Это позволяет спокойно обновлять код, не пересоздавая базу вручную.
    """
    with engine.connect() as conn:
        existing_columns = [row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))]
        if column not in existing_columns:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}"))
            conn.commit()


ensure_column("users", "position", "VARCHAR")


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
        position=user.position,
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
    error: Optional[str] = None,
    err_user: Optional[int] = None,
    err_needed: Optional[int] = None,
    err_available: Optional[int] = None,
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
    position: Optional[str] = Form(None),
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
        position=(position.strip() if position and position.strip() else None),
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


# --- КАЛЕНДАРЬ ОТСУТСТВИЙ (диаграмма Ганта: отпуска, больничные, отгулы) ---

MONTHS_RU = [
    "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
]
WEEKDAYS_RU = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


def shift_month(year: int, month: int, delta: int):
    """Сдвигает год/месяц на delta месяцев (может быть отрицательным)."""
    idx = (year * 12 + (month - 1)) + delta
    return idx // 12, idx % 12 + 1


def ru_days_word(n: int) -> str:
    """Правильное склонение слова 'день' под число (1 день, 2 дня, 5 дней)."""
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} день"
    if 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
        return f"{n} дня"
    return f"{n} дней"


def format_date_range(d1: date, d2: date) -> str:
    """'2 - 6 ноября' или, если период задевает два месяца, '30 нояб. - 2 дек.'"""
    if d1 == d2:
        return f"{d1.day} {MONTHS_RU[d1.month - 1]}"
    if d1.year == d2.year and d1.month == d2.month:
        return f"{d1.day} - {d2.day} {MONTHS_RU[d1.month - 1]}"
    return f"{d1.day} {MONTHS_RU[d1.month - 1]} - {d2.day} {MONTHS_RU[d2.month - 1]}"


@app.get("/admin/calendar", tags=["Web интерфейс"])
def absence_calendar(
    request: Request,
    start: Optional[str] = None,
    months: int = 2,
    db: Session = Depends(get_db),
):
    today = date.today()

    # Какой месяц показывать первым. По умолчанию - текущий.
    if start:
        try:
            start_year, start_month = map(int, start.split("-"))
        except (ValueError, AttributeError):
            start_year, start_month = today.year, today.month
    else:
        start_year, start_month = today.year, today.month

    months = max(1, min(months, 4))  # разумные границы, чтобы не сломать вёрстку

    first_day = date(start_year, start_month, 1)
    last_month_year, last_month_num = shift_month(start_year, start_month, months - 1)
    last_day = date(
        last_month_year, last_month_num,
        calendar_module.monthrange(last_month_year, last_month_num)[1]
    )

    # Список всех дней диапазона (для "шапки" таблицы)
    all_days = []
    cur = first_day
    while cur <= last_day:
        all_days.append(cur)
        cur += timedelta(days=1)

    # Разбивка по месяцам (для верхней строки шапки, "ноябрь", "декабрь"...)
    month_headers = []
    cur_key = None
    for d in all_days:
        key = (d.year, d.month)
        if key != cur_key:
            month_headers.append({"label": f"{MONTHS_RU[d.month - 1]} {d.year}", "span": 1})
            cur_key = key
        else:
            month_headers[-1]["span"] += 1

    day_cells = [
        {
            "num": d.day,
            "weekday": WEEKDAYS_RU[d.weekday()],
            "is_weekend": d.weekday() >= 5,
            "is_today": d == today,
            "col": i + 2,  # +2: первая колонка грид-таблицы занята именами сотрудников
        }
        for i, d in enumerate(all_days)
    ]

    range_start, range_end = all_days[0], all_days[-1]

    # Сотрудники, сгруппированные по должности (как в прототипе)
    users = db.query(models.User).order_by(models.User.position, models.User.full_name).all()

    # Все отсутствия, которые хотя бы частично попадают в видимый диапазон дат.
    # Отклонённые заявки на календаре не показываем - они больше не актуальны.
    absences = db.query(models.AbsenceRequest).filter(
        models.AbsenceRequest.status != models.RequestStatusEnum.REJECTED,
        models.AbsenceRequest.start_date <= range_end,
        models.AbsenceRequest.end_date >= range_start,
    ).all()

    bars_by_user = {}
    currently_away_ids = set()

    for a in absences:
        # a.start_date/a.end_date на уровне модели описаны как Column(Date), поэтому
        # статический анализатор (Pylance) видит их тип как "Column[date]" и путается.
        # На самом деле на конкретной записи "a" это уже обычные значения date -
        # cast() ничего не меняет в рантайме, а просто подсказывает это Pylance.
        a_start = cast(date, a.start_date)
        a_end = cast(date, a.end_date)

        # Обрезаем полосу по границам видимого диапазона (если отпуск начался раньше/закончится позже)
        visible_start = max(a_start, range_start)
        visible_end = min(a_end, range_end)
        offset = (visible_start - range_start).days
        span = (visible_end - visible_start).days + 1

        a_type = str(a.absence_type).split(".")[-1]
        a_status = str(a.status).split(".")[-1]

        if a_type == "VACATION" and a_status == "PENDING":
            css_class = "bar-planned"       # планируемый отпуск - синий
        elif a_type == "VACATION" and a_status == "APPROVED":
            css_class = "bar-approved"      # отпуск согласован - зелёный
        else:
            css_class = "bar-other"         # больничный / отгул (любой статус) - серый

        total_days = (a_end - a_start).days + 1
        show_label = total_days >= 2  # для однодневных отсутствий полоса слишком узкая для текста

        bars_by_user.setdefault(a.user_id, []).append({
            "col_start": offset + 2,
            "span": span,
            "css_class": css_class,
            "days_label": ru_days_word(total_days) if show_label else "",
            "range_label": format_date_range(a_start, a_end) if show_label else "",
        })

        if a_status == "APPROVED" and a_start <= today <= a_end:
            currently_away_ids.add(a.user_id)

    # Группировка сотрудников по должности + сквозная нумерация строк грид-таблицы
    # (строка 1 - месяцы, строка 2 - числа/дни недели, дальше группы и сотрудники)
    row_cursor = 3
    groups = []
    group_index = {}
    for u in users:
        # Та же история, что и с датами: u.position на уровне модели - Column(String),
        # приводим к обычному Optional[str], чтобы можно было писать "if position:".
        position_value = cast(Optional[str], u.position)
        key = position_value.strip() if position_value and position_value.strip() else "Без указанной должности"
        if key not in group_index:
            groups.append({"name": key, "row": row_cursor, "employees": []})
            group_index[key] = len(groups) - 1
            row_cursor += 1
        g = groups[group_index[key]]
        employee_bars = bars_by_user.get(u.id, [])
        for bar in employee_bars:
            bar["row"] = row_cursor
        g["employees"].append({"user": u, "row": row_cursor, "bars": employee_bars})
        row_cursor += 1

    total_rows = row_cursor - 1

    prev_year, prev_month = shift_month(start_year, start_month, -1)
    next_year, next_month = shift_month(start_year, start_month, 1)

    return templates.TemplateResponse(
        request=request,
        name="calendar.html",
        context={
            "request": request,
            "month_headers": month_headers,
            "day_cells": day_cells,
            "groups": groups,
            "total_days": len(all_days),
            "total_rows": total_rows,
            "currently_away_count": len(currently_away_ids),
            "total_employees": len(users),
            "prev_start": f"{prev_year:04d}-{prev_month:02d}",
            "next_start": f"{next_year:04d}-{next_month:02d}",
            "today_start": f"{today.year:04d}-{today.month:02d}",
            "range_title": (
                month_headers[0]["label"] if len(month_headers) == 1
                else f"{month_headers[0]['label']} - {month_headers[-1]['label']}"
            ),
        }
    )
