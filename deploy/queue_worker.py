"""Serial CLI polling keeps heavy jobs from competing on small servers."""
import os
import subprocess
import sys
import time

commands = ["parse-next", "segment-next", "publish-next", "run-report-export-next"]
if os.getenv("TCM_OUTBOUND_MODE", "LOCAL_ONLY") == "CLOUD_ALLOWED":
    commands.append("run-research-next")
while True:
    for command in commands:
        result = subprocess.run([sys.executable, "-m", "tcm_platform.cli", command],
                                check=False)
        if result.returncode:
            print(f"queue command failed: {command} (exit {result.returncode})", flush=True)
    time.sleep(3)
