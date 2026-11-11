"""Configuration for the Jay's Graphic Arts full-auto pipeline.

All settings come from environment variables (see .env.example).
No secrets live in code. The business name is a single constant so a
rename is a one-line change.
"""
import os

# NOTE (2026-10-28): John said "Jace" in chat; the registered business
# name on file is Jay's Graphic Arts (legal: Jays Graphic Arts LLC).
# If Jace is the new name, change this one line.
BUSINESS_NAME = "Jay's Graphic Arts"
BUSINESS_LEGAL_NAME = "Jays Graphic Arts LLC"

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
DRAFTING_API_KEY = os.environ.get("DRAFTING_API_KEY", "")
DRAFTING_ENGINE = os.environ.get("DRAFTING_ENGINE", "mock")  # mock | api

DEPOSIT_PERCENT = 35
REVISION_LIMITS = {
    "Quick Creative Help": 2,  # portfolio process: 2 rounds standard
    "Logo Launch": 2,
    "Business Brand": 3,
    "Brand & Social Launch": 3,
    "Short-form Edit": 2,
    "Social Video Pack": 0,  # monthly bundle, not revision-counted
    "Brand Story Edit": 2,
}
PACKAGE_PRICES = {  # cents, from the published site price list
    "Quick Creative Help": 7500,  # site: from $75
    "Logo Launch": 35000,
    "Business Brand": 75000,
    "Brand & Social Launch": 125000,
    "Short-form Edit": 12500,
    "Social Video Pack": 42500,
    "Brand Story Edit": 65000,
}

PHASE = os.environ.get("JGA_PHASE", "A")  # A = supervised, B = full auto
ERROR_RATE_THRESHOLD = float(os.environ.get("JGA_ERROR_THRESHOLD", "0.05"))
ERROR_RATE_MIN_SAMPLES = int(os.environ.get("JGA_ERROR_MIN_SAMPLES", "20"))
