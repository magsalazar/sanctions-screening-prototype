from datetime import datetime
from pathlib import Path
import subprocess
import sys


def main():
    project_dir = Path(__file__).resolve().parent
    log_dir = project_dir / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"daily-refresh-{datetime.now():%Y-%m-%d}.log"
    ingest_script = project_dir / "ingest.py"

    with log_file.open("a", encoding="utf-8") as output:
        output.write(f"\n[{datetime.now().astimezone().isoformat()}] Starting daily refresh\n")
        output.flush()
        result = subprocess.run(
            [sys.executable, str(ingest_script)],
            cwd=str(project_dir),
            stdout=output,
            stderr=subprocess.STDOUT,
            check=False,
        )
        output.write(
            f"[{datetime.now().astimezone().isoformat()}] "
            f"Refresh process exited with code {result.returncode}\n"
        )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
