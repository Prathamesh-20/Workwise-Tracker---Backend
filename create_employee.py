"""
Create employee user
"""

import asyncio
from app.database import async_session_maker
from app.users import create_user_async
from app.schemas import UserRole


async def create_employee():
    """Create employee user"""
    
    EMAIL = "vinayak.shukla@autonex360.com"
    PASSWORD = "Test@123"  # You can change this
    NAME = "Vinayak Shukla"
    
    async with async_session_maker() as db:
        try:
            user = await create_user_async(
                db=db,
                email=EMAIL,
                password=PASSWORD,
                name=NAME,
                role=UserRole.employee,
                is_approved=True
            )
            
            await db.commit()
            
            print("✅ User created successfully!")
            print(f"   Email: {EMAIL}")
            print(f"   Password: {PASSWORD}")
            
        except Exception as e:
            await db.rollback()
            if "unique constraint" in str(e).lower() or "duplicate" in str(e).lower():
                print("ℹ️  User already exists!")
            else:
                print(f"❌ Error: {e}")


if __name__ == "__main__":
    asyncio.run(create_employee())
