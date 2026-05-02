from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
STORAGE_DIR = ROOT_DIR / "storage"
RUNS_DIR = STORAGE_DIR / "runs"
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"

OFAC_URL = "https://sanctionssearch.ofac.treas.gov/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
)
