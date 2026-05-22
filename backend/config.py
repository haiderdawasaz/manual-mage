# backend/config.py
#
# All secrets come from environment variables — never hardcode values here.
# Local dev:     set via shell before running uvicorn
# HF Spaces:     set via Space Settings → Secrets
# Firebase SA:   set FIREBASE_CREDENTIALS_JSON to the full service account JSON
#                (minified to a single line)

import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Required secrets ──────────────────────────────────────────────────────────
# FIREBASE_CREDENTIALS_JSON: str = "secrets/firebase_config.json"
FIREBASE_CREDENTIALS_JSON: str | None = os.environ.get("FIREBASE_CREDENTIALS_JSON")

# def get_secret(secret_id: str, default: str = "") -> str:
#     """Fetch secret from Google Cloud Secret Manager or fallback to env var."""
#     # Attempt to get from Environment first (local dev)
#     env_val = os.environ.get(secret_id)
#     if env_val:
#         return env_val

#     try:
#         client = secretmanager.SecretManagerServiceClient()
#         # Parse project_id from firebase credentials
#         cred_dict = json.loads(FIREBASE_CREDENTIALS_JSON)
#         project_id = cred_dict.get("project_id")
#         if not project_id:
#             return default
            
#         name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
#         response = client.access_secret_version(request={"name": name})
#         return response.payload.data.decode("UTF-8")
#     except Exception as exc:
#         logger.warning("Could not fetch secret %s from Secret Manager: %s", secret_id, exc)
#         return default

GEMINI_API_KEY: str | None = os.environ.get("GEMINI_API_KEY")

# ── Paths ─────────────────────────────────────────────────────────────────────
# This gets the directory where your script is located
# BASE_DIR = Path(__file__).resolve().parent 

# This creates 'tmp/jobs' inside your project folder
# JOBS_BASE_DIR = BASE_DIR / "tmp" / "jobs"
JOBS_BASE_DIR: Path = Path("/tmp/jobs")
JOBS_BASE_DIR.mkdir(parents=True, exist_ok=True)

# ── Model identifiers ─────────────────────────────────────────────────────────
HF_MODEL_ID: str = "openai/clip-vit-base-patch32"
GEMINI_MODEL_ID: str = "gemini-3-flash-preview"

# ── ASR (Qwen3-ASR) ─────────────────────────────────────────────────────────
LOCAL_ASR_MODEL_ID: str = "Qwen/Qwen3-ASR-0.6B"


# ── Pipeline tuning ───────────────────────────────────────────────────────────
MAX_FRAME_WIDTH_PX: int = 1024
AUDIO_CHUNK_SECONDS: int = 30
DOWNLOAD_EXPIRY_SECONDS: int = 600      # 10 minutes
DEDUP_VISUAL_TOKEN_BUDGET: int = 140
MAX_INFERENCE_RETRIES: int = 3
FRAMES_PER_SECOND: int = 1

# ── CORS ──────────────────────────────────────────────────────────────────────
# Add your Firebase Hosting domain here before deploying.
# Format: https://{project-id}.web.app  OR  https://{custom-domain}
_hosting_domain: str = os.environ.get("FRONTEND_URL", "")

ALLOWED_ORIGINS: list[str] = [
    "http://localhost:4200",
    "https://localhost:4200",
]

if _hosting_domain:
    ALLOWED_ORIGINS.append(_hosting_domain)