# TaskFlow Backend

Initial Django REST API setup for the TaskFlow take-home POC.

## Local Setup

Use Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Update `.env` with local PostgreSQL credentials, then run:

```bash
python manage.py check
python manage.py migrate
python manage.py runserver
```
