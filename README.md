# Tally CRM backend

FastAPI + SQLAlchemy API for the Tally mock CRM. Creates its tables and seeds mock data on first start.

```bash
DATABASE_URL=postgresql://crm:crm@localhost:5432/crm uv run uvicorn app.main:app --reload
```

Container: `docker build -t crm-backend .` (listens on `$PORT`, default 8000).
