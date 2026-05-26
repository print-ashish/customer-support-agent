import sys
import os
import asyncio
import datetime
from sqlalchemy import select
from sqlalchemy.sql import func

# Add backend directory to sys.path so we can import from backend modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.session import async_session_maker, engine
from db.models import User, Order, Base
from auth.jwt import get_password_hash
from sqlalchemy import text

async def seed_data():
    print("Starting database seeding...")
    
    # Run auto-migrations first to ensure all tables and columns exist
    async with engine.begin() as conn:
        print("Running migrations...")
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
        
        # Add columns if not exists
        try:
            await conn.execute(text("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS session_id VARCHAR UNIQUE"))
        except Exception as e:
            print(f"Migration note (conversations): {e}")

        try:
            await conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS item_name VARCHAR"))
            await conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS item_category VARCHAR"))
            await conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS tracking_number VARCHAR"))
            await conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivered_at TIMESTAMP WITH TIME ZONE"))
            await conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS cancellation_reason VARCHAR"))
            await conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMP WITH TIME ZONE"))
            await conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS refunded_at TIMESTAMP WITH TIME ZONE"))
        except Exception as e:
            print(f"Migration note (orders): {e}")

        try:
            await conn.execute(text("ALTER TABLE escalations ADD COLUMN IF NOT EXISTS category VARCHAR"))
            await conn.execute(text("ALTER TABLE escalations ADD COLUMN IF NOT EXISTS user_id INTEGER"))
        except Exception as e:
            print(f"Migration note (escalations): {e}")

    async with async_session_maker() as db:
        # 1. Ensure we have at least one test user
        result = await db.execute(select(User).filter(User.email == "test@example.com"))
        user = result.scalars().first()
        
        if not user:
            print("Creating test user: test@example.com")
            hashed_pw = get_password_hash("password")
            user = User(email="test@example.com", password_hash=hashed_pw)
            db.add(user)
            await db.commit()
            await db.refresh(user)
        else:
            print(f"Found existing test user: test@example.com (ID: {user.id})")

        # 2. Clear existing orders with IDs 1-8 to have a clean, reproducible state
        print("Clearing existing test orders (IDs 1-8)...")
        for oid in [1, 2, 3, 4, 5, 6, 7, 8]:
            result_ord = await db.execute(select(Order).filter(Order.id == oid))
            existing_ord = result_ord.scalars().first()
            if existing_ord:
                await db.delete(existing_ord)
        await db.commit()

        # 3. Create the 8 test orders
        now = datetime.datetime.now(datetime.timezone.utc)
        
        orders_to_create = [
            # Order 1: Wireless Headphones (processing, cancel allowed)
            Order(
                id=1,
                user_id=user.id,
                item_name="Wireless Headphones",
                item_category="electronics",
                status="processing",
                amount=99.99,
                tracking_number=None,
                days_since_delivery=None,
                delivered_at=None,
            ),
            # Order 2: Running Shoes (shipped, cancel allowed with warning)
            Order(
                id=2,
                user_id=user.id,
                item_name="Running Shoes",
                item_category="clothing",
                status="shipped",
                amount=120.00,
                tracking_number="TRK123456789",
                days_since_delivery=None,
                delivered_at=None,
            ),
            # Order 3: Laptop (delivered 5 days ago, refund allowed)
            Order(
                id=3,
                user_id=user.id,
                item_name="Laptop",
                item_category="electronics",
                status="delivered",
                amount=1299.99,
                tracking_number="TRK987654321",
                days_since_delivery=5,
                delivered_at=now - datetime.timedelta(days=5),
            ),
            # Order 4: Organic Juice Pack (delivered 2 days ago, perishable, refund blocked)
            Order(
                id=4,
                user_id=user.id,
                item_name="Organic Juice Pack",
                item_category="perishable",
                status="delivered",
                amount=24.50,
                tracking_number="TRK456123789",
                days_since_delivery=2,
                delivered_at=now - datetime.timedelta(days=2),
            ),
            # Order 5: Custom Phone Case (delivered 10 days ago, personalized, refund blocked)
            Order(
                id=5,
                user_id=user.id,
                item_name="Custom Phone Case",
                item_category="personalized",
                status="delivered",
                amount=35.00,
                tracking_number="TRK789123456",
                days_since_delivery=10,
                delivered_at=now - datetime.timedelta(days=10),
            ),
            # Order 6: Gaming Chair (delivered 45 days ago, expired window, refund blocked)
            Order(
                id=6,
                user_id=user.id,
                item_name="Gaming Chair",
                item_category="furniture",
                status="delivered",
                amount=299.00,
                tracking_number="TRK321654987",
                days_since_delivery=45,
                delivered_at=now - datetime.timedelta(days=45),
            ),
            # Order 7: Bluetooth Speaker (already refunded 20 days ago)
            Order(
                id=7,
                user_id=user.id,
                item_name="Bluetooth Speaker",
                item_category="electronics",
                status="refunded",
                amount=59.99,
                tracking_number="TRK555444333",
                days_since_delivery=20,
                delivered_at=now - datetime.timedelta(days=21),
                refunded_at=now - datetime.timedelta(days=20),
            ),
            # Order 8: Yoga Mat (already cancelled)
            Order(
                id=8,
                user_id=user.id,
                item_name="Yoga Mat",
                item_category="fitness",
                status="cancelled",
                amount=45.00,
                tracking_number=None,
                days_since_delivery=None,
                delivered_at=None,
                cancellation_reason="Customer changed mind",
                cancelled_at=now - datetime.timedelta(days=1),
            ),
        ]

        print("Adding 8 lifecycle test orders...")
        db.add_all(orders_to_create)
        await db.commit()
        print("Database seeded successfully!")

if __name__ == "__main__":
    asyncio.run(seed_data())
