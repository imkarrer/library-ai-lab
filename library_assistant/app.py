from fastapi import FastAPI

app = FastAPI(title="Library Assistant")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
