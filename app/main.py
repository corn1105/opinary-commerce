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

# Mockups live in a separate (potentially volume-mounted) directory so they
# survive Railway redeploys. On first boot of a fresh volume, seed it with
# any mocks bundled in the image. Mount /static/mocks BEFORE /static so the
# more-specific path takes precedence in Starlette's mount routing.
from app.services.mockup_service import MOCKS_DIR, SEED_MOCKS_DIR

MOCKS_DIR.mkdir(parents=True, exist_ok=True)
if SEED_MOCKS_DIR.exists() and SEED_MOCKS_DIR.resolve() != MOCKS_DIR.resolve():
    for src in SEED_MOCKS_DIR.glob("*.html"):
        dst = MOCKS_DIR / src.name
        if not dst.exists():
            dst.write_bytes(src.read_bytes())

app.mount("/static/mocks", StaticFiles(directory=str(MOCKS_DIR)), name="mocks")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(public_router)
app.include_router(admin_router)


@app.get("/health")
async def health():
    return {"status": "ok", "version": app.version}


@app.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse(url="/admin/")
