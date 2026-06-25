"""
All configuration constants — edit here or via the Settings UI.
"""

# Ollama / Model
OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "gemma3"

# Parallel workers
# 6-8 with GPU; 2-3 for CPU-only; 1 to disable parallelism.
WORKERS = 2

# Retry / timeout
MAX_RETRIES = 3
RETRY_BACKOFF = 5       # seconds; doubles each retry
REQUEST_TIMEOUT = 180   # seconds per single HTTP request

# Data defaults
DEFAULT_DAYS_BACK = 7   # None = no date filter
DEFAULT_LIMIT = 20      # None = no limit
MAX_MESSAGE_CHARS = 4000

DEFAULT_EXCEL_FILE = "MessageCenters.xlsx"

# Enum values (editable via Settings UI)
TYP_VALUES = [
    "maintenance", "new_feature", "breaking_change",
    "service_update", "deprecation", "security", "unclear",
]
PRIORYTET_VALUES = ["high", "medium", "low"]
SERWIS_VALUES = [
    "Power Apps", "Power Automate", "Dataverse",
    "Copilot", "Power Pages", "inne",
]
AKCJA_VALUES = ["required", "recommended", "none"]
STATUS_VALUES = ["open", "closed"]

# Persistence files
CHECKPOINT_FILE = "checkpoint.json"
FEEDBACK_FILE = "feedback.json"

# Few-shot feedback
MAX_EXAMPLES = 3

# Web server
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8765
