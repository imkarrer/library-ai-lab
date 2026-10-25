from fastapi import FastAPI

from library_assistant.access import router as access_router
from library_assistant.routers.session import router as session_router

app = FastAPI(title="Library Assistant")
app.include_router(access_router)
app.include_router(session_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
