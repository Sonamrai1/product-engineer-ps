import os

WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "http://localhost:9000/receive")
MAX_ATTEMPTS = int(os.environ.get("MAX_ATTEMPTS", "6"))
BASE_DELAY = float(os.environ.get("BASE_DELAY", "1"))
DB_PATH = os.environ.get("DB_PATH", "webhook.db")
