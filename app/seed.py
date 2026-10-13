"""Mock data so the CRM has something to show on first run."""

import random
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Activity, Company, Contact, Deal

COMPANIES = [
    ("Arunika Logistik", "Logistics", "Jakarta", "arunika-logistik.co.id"),
    ("Sagara Foods", "Food & beverage", "Surabaya", "sagarafoods.id"),
    ("Kirana Health", "Healthcare", "Bandung", "kiranahealth.id"),
    ("Batik Lestari", "Retail", "Yogyakarta", "batiklestari.com"),
    ("Nusa Fintech", "Financial services", "Jakarta", "nusafintech.id"),
    ("Semeru Konstruksi", "Construction", "Malang", "semeru-konstruksi.co.id"),
    ("Cakra Edukasi", "Education", "Semarang", "cakraedukasi.sch.id"),
    ("Pelita Energi", "Energy", "Balikpapan", "pelitaenergi.co.id"),
    ("Rimba Media", "Media", "Denpasar", "rimbamedia.id"),
    ("Tirta Agro", "Agriculture", "Medan", "tirtaagro.co.id"),
]

FIRST = ["Ayu", "Budi", "Citra", "Dimas", "Eka", "Fajar", "Gita", "Hendra", "Intan", "Joko",
         "Kartika", "Lukas", "Maya", "Nanda", "Oki", "Putri", "Rizky", "Sari", "Teguh", "Wulan"]
LAST = ["Santoso", "Wijaya", "Pratama", "Halim", "Kusuma", "Saputra", "Hartono", "Siregar",
        "Lestari", "Nugroho", "Tanjung", "Wibowo"]
TITLES = ["CEO", "CTO", "Head of IT", "Procurement Manager", "Operations Director",
          "Finance Manager", "IT Manager", "Founder"]
DEAL_KINDS = ["Cloud migration", "Managed Kubernetes", "Object storage", "Backup plan",
              "Dedicated server", "CDN rollout", "Database hosting", "Annual support renewal"]
STAGE_WEIGHTS = {"lead": 6, "qualified": 5, "proposal": 4, "negotiation": 3, "won": 4, "lost": 2}
SUBJECTS = {
    "call": ["Discovery call", "Follow-up call", "Pricing check-in"],
    "email": ["Send proposal", "Share case study", "Confirm requirements"],
    "meeting": ["Onsite demo", "Technical workshop", "Contract review"],
    "task": ["Prepare quote", "Update forecast", "Draft SOW"],
}


def seed_if_empty(session: Session) -> None:
    if session.scalar(select(func.count()).select_from(Company)):
        return

    rng = random.Random(42)
    today = date.today()

    companies = [Company(name=n, industry=i, city=c, website=w) for n, i, c, w in COMPANIES]
    session.add_all(companies)
    session.flush()

    contacts: list[Contact] = []
    used = set()
    for company in companies:
        for _ in range(rng.randint(2, 4)):
            while True:
                first, last = rng.choice(FIRST), rng.choice(LAST)
                if (first, last) not in used:
                    used.add((first, last))
                    break
            domain = company.website
            contacts.append(Contact(
                first_name=first, last_name=last,
                email=f"{first}.{last}@{domain}".lower(),
                phone=f"+62 8{rng.randint(11, 59)} {rng.randint(1000, 9999)} {rng.randint(1000, 9999)}",
                title=rng.choice(TITLES), company=company,
            ))
    session.add_all(contacts)
    session.flush()

    stages = list(STAGE_WEIGHTS)
    weights = list(STAGE_WEIGHTS.values())
    deals: list[Deal] = []
    for _ in range(24):
        contact = rng.choice(contacts)
        stage = rng.choices(stages, weights)[0]
        offset = rng.randint(-60, -1) if stage in ("won", "lost") else rng.randint(-5, 75)
        deals.append(Deal(
            title=f"{rng.choice(DEAL_KINDS)} for {contact.company.name}",
            value=Decimal(rng.randrange(15, 900) * 1_000_000),
            stage=stage,
            expected_close=today + timedelta(days=offset),
            company=contact.company, contact=contact,
        ))
    session.add_all(deals)
    session.flush()

    activities = []
    for _ in range(30):
        deal = rng.choice(deals)
        kind = rng.choice(list(SUBJECTS))
        due = today + timedelta(days=rng.randint(-10, 14))
        activities.append(Activity(
            type=kind, subject=rng.choice(SUBJECTS[kind]),
            notes=None, due_date=due,
            done=due < today and rng.random() < 0.6,
            contact=deal.contact, deal=deal,
        ))
    session.add_all(activities)
    session.commit()
