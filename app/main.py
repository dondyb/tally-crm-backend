from contextlib import asynccontextmanager
from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from . import schemas
from .db import Base, SessionLocal, engine, get_session
from .models import DEAL_STAGES, OPEN_STAGES, Activity, Company, Contact, Deal
from .netcheck import report as netcheck_report
from .seed import seed_if_empty


@asynccontextmanager
async def lifespan(_: FastAPI):
    netcheck_report()
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        seed_if_empty(session)
    yield


app = FastAPI(title="CRM API", lifespan=lifespan)
DB = Annotated[Session, Depends(get_session)]


def _commit(session: Session, obj):
    session.add(obj)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409, "A record with the same unique value already exists.") from exc
    session.refresh(obj)
    return obj


def _require(session: Session, model, obj_id: int | None, label: str):
    if obj_id is not None and session.get(model, obj_id) is None:
        raise HTTPException(422, f"{label} {obj_id} does not exist.")


@app.get("/api/health")
def health(session: DB):
    session.execute(select(1))
    return {"ok": True}


# Dashboard ----------------------------------------------------------------

@app.get("/api/dashboard", response_model=schemas.Dashboard)
def dashboard(session: DB):
    today = date.today()

    rows = session.execute(
        select(Deal.stage, func.count(), func.coalesce(func.sum(Deal.value), 0)).group_by(Deal.stage)
    ).all()
    by_stage = {stage: (count, value) for stage, count, value in rows}
    stages = [
        schemas.StageSummary(stage=s, count=by_stage.get(s, (0, 0))[0], value=by_stage.get(s, (0, 0))[1])
        for s in DEAL_STAGES
    ]
    open_stages = [s for s in stages if s.stage in OPEN_STAGES]
    won, lost = by_stage.get("won", (0, 0))[0], by_stage.get("lost", (0, 0))[0]

    won_last_90_days = session.scalar(
        select(func.coalesce(func.sum(Deal.value), 0)).where(
            Deal.stage == "won", Deal.expected_close >= today - timedelta(days=90)
        )
    )
    closing_soon = session.scalars(
        select(Deal)
        .options(selectinload(Deal.company), selectinload(Deal.contact))
        .where(Deal.stage.in_(OPEN_STAGES), Deal.expected_close <= today + timedelta(days=30))
        .order_by(Deal.expected_close)
        .limit(6)
    ).all()
    upcoming = session.scalars(
        select(Activity)
        .options(selectinload(Activity.contact), selectinload(Activity.deal))
        .where(Activity.done.is_(False))
        .order_by(Activity.due_date.nulls_last())
        .limit(8)
    ).all()

    return schemas.Dashboard(
        open_pipeline_value=sum((s.value for s in open_stages), Decimal(0)),
        open_deal_count=sum(s.count for s in open_stages),
        won_value_last_90_days=won_last_90_days,
        win_rate=won / (won + lost) if won + lost else 0.0,
        contact_count=session.scalar(select(func.count()).select_from(Contact)),
        company_count=session.scalar(select(func.count()).select_from(Company)),
        overdue_activity_count=session.scalar(
            select(func.count()).select_from(Activity).where(
                Activity.done.is_(False), Activity.due_date < today
            )
        ),
        stages=stages,
        closing_soon=closing_soon,
        upcoming_activities=upcoming,
    )


# Companies ----------------------------------------------------------------

@app.get("/api/companies", response_model=list[schemas.CompanyOut])
def list_companies(session: DB, q: str | None = None):
    contact_count = (
        select(func.count()).where(Contact.company_id == Company.id).correlate(Company).scalar_subquery()
    )
    open_value = (
        select(func.coalesce(func.sum(Deal.value), 0))
        .where(Deal.company_id == Company.id, Deal.stage.in_(OPEN_STAGES))
        .correlate(Company)
        .scalar_subquery()
    )
    stmt = select(Company, contact_count, open_value).order_by(Company.name)
    if q:
        stmt = stmt.where(or_(Company.name.ilike(f"%{q}%"), Company.industry.ilike(f"%{q}%"),
                              Company.city.ilike(f"%{q}%")))
    return [
        schemas.CompanyOut.model_validate(c).model_copy(update={"contact_count": n, "open_deal_value": v})
        for c, n, v in session.execute(stmt).all()
    ]


@app.post("/api/companies", response_model=schemas.CompanyOut, status_code=201)
def create_company(body: schemas.CompanyIn, session: DB):
    return _commit(session, Company(**body.model_dump()))


# Contacts -----------------------------------------------------------------

@app.get("/api/contacts", response_model=list[schemas.ContactOut])
def list_contacts(session: DB, q: str | None = None, company_id: int | None = None):
    stmt = select(Contact).options(selectinload(Contact.company)).order_by(Contact.first_name, Contact.last_name)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Contact.first_name.ilike(like), Contact.last_name.ilike(like),
                              Contact.email.ilike(like), Contact.title.ilike(like)))
    if company_id:
        stmt = stmt.where(Contact.company_id == company_id)
    return session.scalars(stmt).all()


@app.post("/api/contacts", response_model=schemas.ContactOut, status_code=201)
def create_contact(body: schemas.ContactIn, session: DB):
    _require(session, Company, body.company_id, "Company")
    return _commit(session, Contact(**body.model_dump()))


# Deals --------------------------------------------------------------------

@app.get("/api/deals", response_model=list[schemas.DealOut])
def list_deals(session: DB, q: str | None = None, stage: schemas.Stage | None = None):
    stage_order = case({s: i for i, s in enumerate(DEAL_STAGES)}, value=Deal.stage)
    stmt = (
        select(Deal)
        .options(selectinload(Deal.company), selectinload(Deal.contact))
        .order_by(stage_order, Deal.expected_close.nulls_last())
    )
    if q:
        stmt = stmt.where(Deal.title.ilike(f"%{q}%"))
    if stage:
        stmt = stmt.where(Deal.stage == stage)
    return session.scalars(stmt).all()


@app.post("/api/deals", response_model=schemas.DealOut, status_code=201)
def create_deal(body: schemas.DealIn, session: DB):
    _require(session, Company, body.company_id, "Company")
    _require(session, Contact, body.contact_id, "Contact")
    return _commit(session, Deal(**body.model_dump()))


@app.patch("/api/deals/{deal_id}/stage", response_model=schemas.DealOut)
def update_deal_stage(deal_id: int, body: schemas.StageUpdate, session: DB):
    deal = session.get(Deal, deal_id)
    if deal is None:
        raise HTTPException(404, f"Deal {deal_id} does not exist.")
    deal.stage = body.stage
    return _commit(session, deal)


# Activities ---------------------------------------------------------------

@app.get("/api/activities", response_model=list[schemas.ActivityOut])
def list_activities(session: DB, status: Annotated[str, Query(pattern="^(open|done|all)$")] = "open"):
    stmt = (
        select(Activity)
        .options(selectinload(Activity.contact), selectinload(Activity.deal))
        .order_by(Activity.due_date.nulls_last(), Activity.id)
    )
    if status == "open":
        stmt = stmt.where(Activity.done.is_(False))
    elif status == "done":
        stmt = stmt.where(Activity.done.is_(True))
    return session.scalars(stmt).all()


@app.post("/api/activities", response_model=schemas.ActivityOut, status_code=201)
def create_activity(body: schemas.ActivityIn, session: DB):
    _require(session, Contact, body.contact_id, "Contact")
    _require(session, Deal, body.deal_id, "Deal")
    return _commit(session, Activity(**body.model_dump()))


@app.patch("/api/activities/{activity_id}/toggle", response_model=schemas.ActivityOut)
def toggle_activity(activity_id: int, session: DB):
    activity = session.get(Activity, activity_id)
    if activity is None:
        raise HTTPException(404, f"Activity {activity_id} does not exist.")
    activity.done = not activity.done
    return _commit(session, activity)
