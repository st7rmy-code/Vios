from fastapi import FastAPI

from app import errors
from app.api import admin, audit, auth, consents, data, experiments, imports

app = FastAPI(title="Сверка API", version="0.2.0")
errors.install(app)
for r in (auth.router, admin.router, consents.router, imports.router, data.router, experiments.router,
          audit.router):
    app.include_router(r, prefix="/api/v1")


@app.get("/health", operation_id="health")
def health() -> dict:
    return {"status": "ok"}
