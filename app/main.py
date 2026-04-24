from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.routes.admin import router as admin_router
from app.routes.public import router as public_router

app = FastAPI(title="OpinaryCommerce", version="0.1.1")

# Compress responses > 1KB — biggest win on the vote payload (~10KB → ~3KB).
app.add_middleware(GZipMiddleware, minimum_size=1000)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(public_router)
app.include_router(admin_router)


@app.get("/health")
async def health():
    return {"status": "ok", "version": app.version}


@app.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse(url="/admin/")
