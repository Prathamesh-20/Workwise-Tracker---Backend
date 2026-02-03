"""
Create default admin user
Run this once to set up your admin account
"""

import asyncio
from app.database import async_session_maker
from app.users import create_user_async
from app.schemas import UserRole


async def create_admin():
    """Create admin user"""
    
    # Admin credentials
    ADMIN_EMAIL = "admin@workwise.com"
    ADMIN_PASSWORD = "admin123"  # Change this after first login!
    ADMIN_NAME = "Administrator"
    
    async with async_session_maker() as db:
        try:
            # Create admin user
            admin = await create_user_async(
                db=db,
                email=ADMIN_EMAIL,
                password=ADMIN_PASSWORD,
                name=ADMIN_NAME,
                role=UserRole.admin,
                is_approved=True
            )
            
            await db.commit()
            
            print("✅ Admin user created successfully!")
            print(f"   Email: {ADMIN_EMAIL}")
            print(f"   Password: {ADMIN_PASSWORD}")
            print("\n⚠️  IMPORTANT: Change the password after first login!")
            
        except Exception as e:
            await db.rollback()
            if "unique constraint" in str(e).lower() or "duplicate" in str(e).lower():
                print("ℹ️  Admin user already exists!")
            else:
                print(f"❌ Error creating admin: {e}")
                raise


if __name__ == "__main__":
    asyncio.run(create_admin())
