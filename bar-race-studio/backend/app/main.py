from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import assets, format, projects, renders, uploads
from app.core.db import init_db
from app.services.folder_watcher import start_watcher

app = FastAPI(title="Bar Race Studio API")
init_db()
start_watcher()

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
app.include_router(format.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
