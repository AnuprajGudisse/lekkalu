# Copyright (c) 2026 Lekkalu
"""Create the three businesses and their customers. Safe to run again.

Usage: uv run python scripts/seed.py [base_url]
Amma's customers come from the git-ignored data/customers.csv (name,name_native) when it exists.
"""
import csv
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.core import database  # noqa: E402
from app.core.models import Business  # noqa: E402
from app.customers import services as customers  # noqa: E402
from app.customers.schemas import DuplicateCustomer  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data"
DEMO_CSV = DATA / "demo_customers.csv"
BUSINESSES = [
    # slug, name, public, customer csv
    ("amma", "Amma's Sarees", False, DATA / "customers.csv"),
    ("practice", "Practice Shop", False, DEMO_CSV),
    ("demo", "Demo Saree Shop", True, DEMO_CSV),
]


def main(base_url: str) -> None:
    with database.SessionLocal() as session, session.begin():
        for slug, name, public, csv_path in BUSINESSES:
            b = session.scalars(select(Business).where(Business.slug == slug)).one_or_none()
            if b is None:
                b = Business(slug=slug, name=name, is_public_demo=public,
                             access_token=None if public else secrets.token_urlsafe(16))
                session.add(b)
                session.flush()
            added = 0
            if csv_path.exists():
                for row in csv.DictReader(csv_path.open(encoding="utf-8")):
                    try:
                        customers.create(session, business_id=b.id, name=row["name"], name_native=row.get("name_native") or None)
                        added += 1
                    except DuplicateCustomer:
                        pass
            else:
                print(f"  ({csv_path.name} not found; no customers for {slug})")
            token = f"?t={b.access_token}" if b.access_token else ""
            print(f"{name}: {base_url}/c/{slug}{token}  (+{added} customers)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000")
