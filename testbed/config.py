"""Central configuration. Everything reads from .env with sane defaults."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DB_PATH = ROOT / "data" / "db.json"
TASKS_PATH = ROOT / "evals" / "tasks.jsonl"
TASKS_HASH_PATH = ROOT / "evals" / "tasks.sha256"
RESULTS_DIR = ROOT / "results"
SERVER_PATH = ROOT / "server" / "orders_server.py"

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq")
LLM_MODEL = os.getenv("LLM_MODEL", "")

FAULT_HANG_SECONDS = float(os.getenv("FAULT_HANG_SECONDS", "20"))
TOOL_TIMEOUT_SECONDS = float(os.getenv("TOOL_TIMEOUT_SECONDS", "8"))
TOOL_RETRIES = int(os.getenv("TOOL_RETRIES", "3"))
TASK_TIMEOUT_SECONDS = float(os.getenv("TASK_TIMEOUT_SECONDS", "120"))
RECURSION_LIMIT = int(os.getenv("RECURSION_LIMIT", "25"))
