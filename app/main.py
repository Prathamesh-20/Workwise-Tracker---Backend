"""
FastAPI Backend - Employee Tracker
Production-grade async API
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.api import auth, logs, status, health, rules, analytics, sync, desktop_analytics, fraud_detection, admin
from app.config import settings
from app.database import init_db
from app.users import create_default_users_async


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    # Startup
    print(f"🚀 Starting Workwise API v{settings.VERSION}")
    print(f"📊 Environment: {settings.ENVIRONMENT}")
    
    # Initialize database tables
    await init_db()
    print("✅ Database initialized")
    
    # Create default users if they don't exist
    await create_default_users_async()
    print("✅ Default users ready")
    
    yield
    
    # Shutdown
    print("👋 Shutting down...")


app = FastAPI(
    title="Workwise API",
    description="Backend API for Workwise Employee Productivity Tracker",
    version=settings.VERSION,
    lifespan=lifespan,
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, tags=["Health"])
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(admin.router, prefix="/api", tags=["Admin"])
app.include_router(logs.router, prefix="/api/logs", tags=["Activity Logs"])
app.include_router(status.router, prefix="/api/status", tags=["Status"])
app.include_router(rules.router, prefix="/api/rules", tags=["Categorization"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics"])
app.include_router(sync.router, prefix="/api", tags=["Desktop Sync"])
app.include_router(desktop_analytics.router, prefix="/api/analytics", tags=["Desktop Analytics"])
app.include_router(fraud_detection.router, prefix="/api", tags=["Fraud Detection"])


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": "Employee Tracker API",
        "version": settings.VERSION,
        "status": "running",
    }
