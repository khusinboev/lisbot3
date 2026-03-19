"""Application settings and environment parsing."""
import os
from pathlib import Path


BASE_URL = "https://license.gov.uz"
API_URL = "https://api.licenses.uz/v2"
DOC_URL = "https://doc.licenses.uz/v1"

DB_PATH = os.getenv("DB_PATH", "data/certificates.db")
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "downloads")
TARGET_ACTIVITY_TYPE = os.getenv("TARGET_ACTIVITY_TYPE", "Олий таълим хизматлари")

SCRAPE_UPDATE_EVERY_PAGES = int(os.getenv("SCRAPE_UPDATE_EVERY_PAGES", "5"))
UPDATE_PROGRESS_EVERY_ITEMS = int(os.getenv("UPDATE_PROGRESS_EVERY_ITEMS", "10"))
DOWNLOAD_PROGRESS_EVERY_ITEMS = int(os.getenv("DOWNLOAD_PROGRESS_EVERY_ITEMS", "5"))

UPDATE_ITEM_DELAY_SECONDS = float(os.getenv("UPDATE_ITEM_DELAY_SECONDS", "0.35"))
DOWNLOAD_ITEM_DELAY_SECONDS = float(os.getenv("DOWNLOAD_ITEM_DELAY_SECONDS", "0.5"))


def parse_admin_ids(raw_value: str) -> list[int]:
    """Parse comma-separated admin IDs safely."""
    admin_ids: list[int] = []
    for item in raw_value.split(","):
        value = item.strip()
        if not value:
            continue
        try:
            admin_ids.append(int(value))
        except ValueError:
            continue
    return admin_ids
