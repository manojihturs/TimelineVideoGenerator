from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import renders, uploads

app = FastAPI(title="Bar Race Studio API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(uploads.router)
app.include_router(renders.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
