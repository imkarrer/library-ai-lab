import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from library_assistant import access, access_log
from library_assistant.access import connect, get_clock
from library_assistant.access import router as access_router
from library_assistant.access_log import AccessLogMiddleware
from library_assistant.dependencies import get_settings
from library_assistant.install_settings import router as install_settings_router
from library_assistant.mint_app import router as mint_app_router

# Import here to avoid circular imports
from library_assistant.oversight import acquire_oversight_lock
from library_assistant.purge import purge_loop, run_if_due
from library_assistant.registration_cors import RegistrationCorsMiddleware
from library_assistant.routers.about import router as about_router
from library_assistant.routers.alarms import router as alarms_router
from library_assistant.routers.catalog_import import router as catalog_import_router
from library_assistant.routers.flags import router as flags_router
from library_assistant.routers.holds import router as holds_router
from library_assistant.routers.it_kit import router as it_kit_router
from library_assistant.routers.lessons import router as lessons_router
from library_assistant.routers.live import router as live_router
from library_assistant.routers.session import router as session_router
from library_assistant.routers.watch import router as watch_router
from library_assistant.staff import StaffSignInRequired, sign_in_required_handler
from library_assistant.staff import router as staff_router
from library_assistant.theme import router as theme_router

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
    settings = app.dependency_overrides.get(get_settings, get_settings)()

    # Check for invalid overrides at startup (ADR-0011)
    from library_assistant.supportive_replies import invalid_overrides

    invalid = invalid_overrides(db)
    if invalid:
        # Raise RuntimeError naming each category and error, as ADR-0011 says
        error_messages = []
        for category, errors in invalid.items():
            error_messages.append(f"{category}: {'; '.join(errors)}")
        raise RuntimeError(f"Invalid overrides found: {', '.join(error_messages)}")

    # Run purge if needed at startup
    run_if_due(db, clock(), settings)

    # Start catch-up if needed after purge
    if settings.oversight_enabled:
        from library_assistant.routers.live import get_live_bus
        from library_assistant.routers.session import start_catch_up_if_needed

        bus = get_live_bus()  # Default bus without overrides
        start_catch_up_if_needed(db, settings, bus, clock, asyncio.sleep)

    # Acquire the Oversight lock if enabled; otherwise Oversight is not configured.
    global _oversight_lock_file, _purge_task
    if settings.oversight_enabled:
        # Beside the database, the Install's own state: the Catalog may be shared, and
        # beside it the lock once landed in the repo checkout.
        _oversight_lock_file = acquire_oversight_lock(access.DB_PATH)

    _purge_task = asyncio.create_task(purge_loop(db, settings, clock, asyncio.sleep))

    yield

    _purge_task.cancel()
    try:
        await _purge_task
    except asyncio.CancelledError:
        pass
    _purge_task = None

    # Cancel the probe task if it exists (ADR-0004 addendum)
    # Import the session module to access _probe_task
    import library_assistant.routers.session as session_module

    if session_module._probe_task is not None:
        session_module._probe_task.cancel()
        try:
            await session_module._probe_task
        except asyncio.CancelledError:
            pass
        session_module._probe_task = None

    if _oversight_lock_file is not None:
        try:
            _oversight_lock_file.close()
        except OSError as e:
            logger.warning(f"Failed to close oversight lock file: {e}")
        _oversight_lock_file = None


app = FastAPI(title="Library Assistant", lifespan=lifespan)
app.include_router(access_router)
app.include_router(session_router)
app.include_router(about_router)
app.include_router(staff_router)
app.include_router(live_router)
app.include_router(flags_router)
app.include_router(holds_router)
app.include_router(catalog_import_router)
app.include_router(install_settings_router)
app.include_router(watch_router)
app.include_router(alarms_router)
app.include_router(theme_router)
app.include_router(it_kit_router)
app.include_router(lessons_router)
app.include_router(mint_app_router)
app.add_exception_handler(StaffSignInRequired, sign_in_required_handler)
# The only access log: route template, status, duration (ADR-0003 addendum).
access_log.configure()
app.add_middleware(AccessLogMiddleware)
# CORS for /batches alone, so the offline Minting page can register (ADR-0002).
app.add_middleware(RegistrationCorsMiddleware)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
