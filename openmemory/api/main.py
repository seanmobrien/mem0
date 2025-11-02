import datetime
import os
from fastapi import FastAPI
from app.database import engine, Base, SessionLocal
from app.mcp_server import setup_mcp_server
from app.routers import memories_router, apps_router, stats_router, config_router, users_router, ping_router
from fastapi_pagination import add_pagination
from fastapi.middleware.cors import CORSMiddleware
from app.models import User, App
from uuid import uuid4
from app.config import USER_ID, DEFAULT_APP_ID
from app.telemetry import init_telemetry
from app.routers import well_known_auth

publicUrl = os.getenv("NEXT_PUBLIC_URL") or "http://localhost:8000"
_telemetry_connection_string = os.getenv("AZURE_MONITOR_CONNECTION_STRING", "")
_telemetry_sampling_ratio = os.getenv("AZURE_MONITOR_SAMPLING_RATIO")

telemetry_tracer = init_telemetry(
    _telemetry_connection_string,
    float(_telemetry_sampling_ratio) if _telemetry_sampling_ratio else None,
)

app = FastAPI(
    title="OpenMemory API", 
    servers=[{"url": publicUrl}], 
    root_path_in_servers=False,
    description="OpenMemory API with Keycloak authentication"
)

if telemetry_tracer:
    # Expose tracer for reuse by application components that need custom spans.
    app.state.telemetry_tracer = telemetry_tracer

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create all tables
Base.metadata.create_all(bind=engine)

# Check for USER_ID and create default user if needed
def create_default_user():
    db = SessionLocal()
    try:
        # Check if user exists
        user = db.query(User).filter(User.user_id == USER_ID).first()
        if not user:
            # Create default user
            user = User(
                id=uuid4(),
                user_id=USER_ID,
                name="Default User",
                created_at=datetime.datetime.now(datetime.UTC)
            )
            db.add(user)
            db.commit()
    finally:
        db.close()


def create_default_app():
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.user_id == USER_ID).first()
        if not user:
            return

        # Check if app already exists
        existing_app = db.query(App).filter(
            App.name == DEFAULT_APP_ID,
            App.owner_id == user.id
        ).first()

        if existing_app:
            return

        app = App(
            id=uuid4(),
            name=DEFAULT_APP_ID,
            owner_id=user.id,
            created_at=datetime.datetime.now(datetime.UTC),
            updated_at=datetime.datetime.now(datetime.UTC),
        )
        db.add(app)
        db.commit()
    finally:
        db.close()

# Create default user on startup
create_default_user()
create_default_app()

# Setup MCP server
setup_mcp_server(app)

# Include routers
app.include_router(memories_router)
app.include_router(apps_router)
app.include_router(stats_router)
app.include_router(config_router)
app.include_router(users_router)
app.include_router(ping_router)
app.include_router(well_known_auth.router)

# Add pagination support
add_pagination(app)
