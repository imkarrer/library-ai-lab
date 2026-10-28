from contextlib import asynccontextmanager

from fastapi import FastAPI

from library_assistant.access import connect, get_clock
from library_assistant.access import router as access_router
from library_assistant.config import Settings
from library_assistant.install_settings import router as install_settings_router

# Import here to avoid circular imports
from library_assistant.purge import run_if_due
from library_assistant.routers.flags import router as flags_router
from library_assistant.routers.live import router as live_router
from library_assistant.routers.session import router as session_router
from library_assistant.staff import StaffSignInRequired, sign_in_required_handler
from library_assistant.staff import router as staff_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager to run purge at startup if needed."""
    # Initialize the database connection
    db = connect()

    # Get the current time and settings using dependency overrides
    clock = app.dependency_overrides.get(get_clock, get_clock)()
    settings = app.dependency_overrides.get(Settings, lambda: Settings())()

    # Run purge if needed at startup
    run_if_due(db, clock, settings)

    yield


app = FastAPI(title="Library Assistant", lifespan=lifespan)
app.include_router(access_router)
app.include_router(session_router)
app.include_router(staff_router)
app.include_router(live_router)
app.include_router(flags_router)
app.include_router(install_settings_router)
app.add_exception_handler(StaffSignInRequired, sign_in_required_handler)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
