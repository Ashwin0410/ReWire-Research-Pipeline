import os
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.core.config import cfg
from app.db import engine, Base
from app.models import ResearchSession  # noqa: F401

app = FastAPI(
    title="ReWire Research Pipeline",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cfg.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


os.makedirs(cfg.out_dir_path, exist_ok=True)
app.mount("/public", StaticFiles(directory=str(cfg.out_dir_path)), name="public")

assets_path = Path(__file__).parent / "assets"
if assets_path.exists():
    app.mount("/assets", StaticFiles(directory=str(assets_path)), name="assets")


@app.on_event("startup")
def on_startup():
    print("[startup] Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("[startup] Database tables created successfully")


from app.routes.research import r as research_r
app.include_router(research_r)


FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "rewire-research"}


@app.get("/")
def serve_root():
    path = FRONTEND_DIR / "index.html"
    if path.exists():
        return FileResponse(str(path), media_type="text/html")
    return {"service": "ReWire Research Pipeline", "endpoints": ["/music", "/speech", "/docs"]}


@app.get("/music")
def serve_music():
    path = FRONTEND_DIR / "music.html"
    if path.exists():
        return FileResponse(str(path), media_type="text/html")
    return {"error": "music.html not found"}


@app.get("/speech")
def serve_speech():
    path = FRONTEND_DIR / "speech.html"
    if path.exists():
        return FileResponse(str(path), media_type="text/html")
    return {"error": "speech.html not found"}