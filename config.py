import os
from dotenv import load_dotenv


# ============================================================
# LOAD ENVIRONMENT
# ============================================================

load_dotenv()


# ============================================================
# BASE PATHS
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

UPLOAD_FOLDER = os.path.join(
    BASE_DIR,
    "uploads"
)

os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)


# ============================================================
# FLASK CONFIG
# ============================================================

FLASK_SECRET_KEY = os.getenv(
    "FLASK_SECRET_KEY",
    "resume_screening_secret_key"
)


# ============================================================
# ALLOWED FILES
# ============================================================

ALLOWED_EXTENSIONS = {
    "pdf",
    "docx",
    "txt",
    "rtf",
    "jpg",
    "jpeg",
    "png",
    "webp"
}


# ============================================================
# GEMINI CONFIG
# ============================================================

GEMINI_API_KEY = os.getenv(
    "GEMINI_API_KEY"
)

GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.8-flash"
)


# ============================================================
# ADZUNA CONFIG
# ============================================================

ADZUNA_APP_ID = os.getenv(
    "ADZUNA_APP_ID"
)

ADZUNA_APP_KEY = os.getenv(
    "ADZUNA_APP_KEY"
)

ADZUNA_COUNTRY = os.getenv(
    "ADZUNA_COUNTRY",
    "in"
)

ADZUNA_BASE_URL = (
    "https://api.adzuna.com/v1/api"
)


# ============================================================
# API VALIDATION
# ============================================================

if not ADZUNA_APP_ID:
    raise RuntimeError(
        "ADZUNA_APP_ID not found in .env"
    )

if not ADZUNA_APP_KEY:
    raise RuntimeError(
        "ADZUNA_APP_KEY not found in .env"
    )