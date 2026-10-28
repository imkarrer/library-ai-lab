import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from library_assistant import access_log
from library_assistant.access import connect, get_clock
from library_assistant.access import router as access_router
from library_assistant.access_log import AccessLogMiddleware
from library_assistant.config import Settings
from library_assistant.install_settings import router as install_settings_router

# Import here to avoid circular imports
from library_assistant.oversight import acquire_oversight_lock
from library_assistant.purge import purge_loop, run_if_due
from library_assistant.routers.flags import router as flags_router
from library_assistant.routers.live import router as live_router
from library_assistant.routers.session import router as session_router
from library_assistant.staff import StaffSignInRequired, sign_in_required_handler
from library_assistant.staff import router as staff_router

logger = logging.getLogger(__name__)

# Keeps the oversight lock file open for the process's life.
_oversight_lock_file = None
_purge_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager to run purge at startup and hold the Oversight lock."""
    # Initialize the database connection
    db = connect()

    # Get the current time and settings using dependency overrides
    clock = app.dependency_overrides.get(get_clock, get_clock)
    settings = app.dependency_overrides.get(Settings, lambda: Settings())()

    # Run purge if needed at startup
    run_if_due(db, clock(), settings)

    # Acquire the Oversight lock if enabled; otherwise Oversight is not configured.
    global _oversight_lock_file, _purge_task
    if settings.oversight_enabled:
        _oversight_lock_file = acquire_oversight_lock(settings.catalog_path)

    _purge_task = asyncio.create_task(purge_loop(db, settings, clock, asyncio.sleep))

    yield

    _purge_task.cancel()
    try:
        await _purge_task
    except asyncio.CancelledError:
        pass
    _purge_task = None

    if _oversight_lock_file is not None:
        try:
            _oversight_lock_file.close()
        except OSError as e:
            logger.warning(f"Failed to close oversight lock file: {e}")
        _oversight_lock_file = None


app = FastAPI(title="Library Assistant", lifespan=lifespan)
app.include_router(access_router)
app.include_router(session_router)
app.include_router(staff_router)
app.include_router(live_router)
app.include_router(flags_router)
app.include_router(install_settings_router)
app.add_exception_handler(StaffSignInRequired, sign_in_required_handler)
# The only access log: route template, status, duration (ADR-0003 addendum).
access_log.configure()
app.add_middleware(AccessLogMiddleware)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
