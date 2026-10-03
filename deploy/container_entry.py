"""Container process entry; bootstrap codes never go to container logs."""
import os
from pathlib import Path
import secrets
import sys

mode = sys.argv[1] if len(sys.argv) > 1 else "api"
if mode == "api":
    code = secrets.token_hex(32)
    path = Path("/run/tcm-bootstrap/code")
    path.write_text(code + "\n", encoding="utf-8")
    path.chmod(0o600)
    os.environ["TCM_BOOTSTRAP_SECRET"] = code
    command = ["uvicorn", "tcm_platform.main:app", "--host", "0.0.0.0",
               "--port", "8000", "--workers", "1"]
elif mode == "worker":
    command = [sys.executable, "/app/deploy/queue_worker.py"]
else:
    command = sys.argv[1:]
os.execvp(command[0], command)
