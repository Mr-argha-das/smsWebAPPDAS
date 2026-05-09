from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse
from contextlib import asynccontextmanager
import logging, os

from config import settings
from database import connect_db, disconnect_db

# Phase 1
from routes.auth import router as auth_router
from routes.institution import router as institution_router
from routes.students import router as student_router
from routes.staff import router as staff_router
from routes.attendance import router as attendance_router
from routes.fees import router as fees_router
from routes.academics import exam_router, academic_router

# Phase 2
from routes.transport import router as transport_router
from routes.library import router as library_router
from routes.other_modules import inventory_router, health_router, communication_router
from routes.reports import router as reports_router

# Phase 3
from routes.hostel import router as hostel_router
from routes.payroll import router as payroll_router
from routes.phase3_modules import admissions_router, cert_router
from routes.parent_portal import router as parent_router
from routes.admin import router as admin_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Paths
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    connect_db()
    for d in ["student_photos", "student_documents", "staff_photos",
              "study_materials", "notices", "assets", "certificates"]:
        os.makedirs(os.path.join(settings.UPLOAD_DIR, d), exist_ok=True)
    logger.info("🚀 Scholar Desk v1.0 — http://localhost:8000")
    logger.info("📄 Frontend : http://localhost:8000/")
    logger.info("📚 API Docs : http://localhost:8000/api/docs")
    yield
    disconnect_db()


app = FastAPI(
    title="EduManage Pro",
    version="3.0.0",
    description="Complete School Management System — 19 Modules",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# ── Mount uploads directory ───────────────────────────────────────────────────
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")
admin_static_dir = os.path.join(BASE_DIR, "static")
if os.path.exists(admin_static_dir):
    app.mount("/admin-assets", StaticFiles(directory=admin_static_dir), name="admin_static")


# ── Global error handler ──────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Don't intercept 404s for static files
    logger.error(f"Error on {request.url}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"success": False, "message": str(exc)}
    )


# ── Register ALL API routers ──────────────────────────────────────────────────
PREFIX = "/api/v1"

app.include_router(admin_router)

for r in [
    auth_router, institution_router, student_router, staff_router,
    attendance_router, fees_router, exam_router, academic_router,
    transport_router, library_router, inventory_router, health_router,
    communication_router, reports_router,
    hostel_router, payroll_router, admissions_router, cert_router,
    parent_router
]:
    app.include_router(r, prefix=PREFIX)


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/api/v1/health", tags=["Health"])
async def health_check():
    return {"status": "healthy", "version": "3.0.0", "modules": 19}


# ── Serve specific HTML pages (must be before static mount) ──────────────────
HTML_PAGES = [
    "login", "dashboard", "institution", "students", "staff", "academics",
    "exams", "fees", "attendance", "transport", "library", "inventory",
    "health", "communication", "reports", "hostel", "payroll", "admissions",
    "certificates", "parent-portal", "parent-login", "apply"
]

@app.get("/", include_in_schema=False)
async def root():
    """Root URL → redirect to login"""
    return RedirectResponse(url="/login.html")

@app.get("/login", include_in_schema=False)
async def login_redirect():
    return RedirectResponse(url="/login.html")

# Serve each .html page without extension too (e.g. /dashboard → dashboard.html)
for page in HTML_PAGES:
    def make_route(p):
        async def route(request: Request):
            file_path = os.path.join(FRONTEND_DIR, f"{p}.html")
            if os.path.exists(file_path):
                return FileResponse(file_path, media_type="text/html")
            return JSONResponse(status_code=404, content={"message": f"Page {p} not found"})
        route.__name__ = f"page_{p.replace('-','_')}"
        return route
    app.get(f"/{page}", include_in_schema=False)(make_route(page))


# ── Mount frontend as static files (serves .html, .js, .css, images) ─────────
# This MUST come LAST so API routes take priority
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
else:
    logger.warning(f"⚠️  Frontend directory not found: {FRONTEND_DIR}")

    @app.get("/", include_in_schema=False)
    async def no_frontend():
        return JSONResponse({"message": "Frontend not found. Place frontend/ folder next to main.py", "api_docs": "/api/docs"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8060, reload=True)
