from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import assets, projects, renders, uploads
from app.core.db import init_db

app = FastAPI(title="Bar Race Studio API")
init_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(uploads.router)
app.include_router(renders.router)
app.include_router(assets.router)
app.include_router(projects.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
