from fastapi import FastAPI

from library_assistant.access import router as access_router

app = FastAPI(title="Library Assistant")
app.include_router(access_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
