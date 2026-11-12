from fastapi import FastAPI

from app.api import admin, audit, auth, experiments, imports

app = FastAPI(title="Сверка API", version="0.1.0")
for r in (auth.router, admin.router, imports.router, experiments.router, audit.router):
    app.include_router(r, prefix="/api/v1")


@app.get("/health", operation_id="health")
def health() -> dict:
    return {"status": "ok"}
