from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import hash_password
from app.models.inventory import Batch, Sku
from app.models.product import Product, ProductVariant
from app.models.program import WellnessProgram
from app.models.user import User
from app.repositories import users as user_repo
from app.services.auth import initials_for


VARIANTS = [
    ("SM-MB-10", 10, 3390, 3890, "Starter", "10-day trial course", 1840, 0, 950),
    ("SM-MB-15", 15, 4990, 5790, "Ritual", "15-day balanced course", 620, 0, 380),
    ("SM-MB-30", 30, 8990, 11390, "Restore", "30-day full course · Best value", 128, 0, 105),
]

PROGRAMS = [
    ("sleep30", "Sleep 30", "A 30-day guided sleep reset — daily audio, sleep journal, weekly check-in.", "30 days", "🌙"),
    ("deep-rest", "Deep Rest", "Focus on unwinding the nervous system — breathwork, evening yoga, doctor calls.", "60 days", "🌿"),
    ("slow-year", "Slow Year", "Year-long companion — quarterly consults, seasonal protocols, community access.", "12 months", "✧"),
]


def seed(db: Session, settings: Settings) -> None:
    email = (settings.seed_founder_email or "").strip().lower()
    password = settings.seed_founder_password or ""
    if email and password:
        founder = user_repo.get_by_email(db, email)
        if founder is None:
            founder = db.scalar(select(User).where(User.role == "founder").order_by(User.id.asc()).limit(1))
        name = email.split("@")[0].replace(".", " ").replace("_", " ").title() or "Founder"
        if founder is None:
            db.add(
                User(
                    email=email,
                    password_hash=hash_password(password),
                    name=name,
                    phone="",
                    role="founder",
                    initials=initials_for(name),
                )
            )
        else:
            founder.email = email
            founder.password_hash = hash_password(password)
            founder.role = "founder"
            founder.name = name
            founder.initials = initials_for(name)
    product = db.query(Product).filter(Product.slug == "slow-mo-gummies").one_or_none()
    if product is None:
        product = Product(
            slug="slow-mo-gummies",
            name="Slow Mo wellness gummies",
            description="Mixed-berry gummies · 3.5mg Vijaya extract each · Ayurvedic proprietary medicine, prescription use only.",
        )
        db.add(product)
        db.flush()
        today = date.today()
        for sku, qty, price, mrp, label, desc, stock, allocated, forecast in VARIANTS:
            variant = ProductVariant(
                product_id=product.id,
                sku=sku,
                qty=qty,
                price=price,
                mrp=mrp,
                label=label,
                description=desc,
            )
            db.add(variant)
            db.flush()
            record = Sku(
                variant_id=variant.id,
                code=sku,
                name=f"Slow Mo · {qty} pack (mixed berry)",
                stock=stock,
                allocated=allocated,
                weekly_forecast=forecast,
            )
            db.add(record)
            db.flush()
            db.add(
                Batch(
                    sku_id=record.id,
                    code=f"B{today.strftime('%y%m')}-{sku[-2:]}",
                    made_on=today - timedelta(days=6),
                    expires_on=today + timedelta(days=359),
                    qty=min(stock, 800),
                )
            )
    existing = {row.key for row in db.query(WellnessProgram).all()}
    for key, name, desc, duration, icon in PROGRAMS:
        if key not in existing:
            db.add(WellnessProgram(key=key, name=name, description=desc, duration=duration, icon=icon))
    db.commit()
