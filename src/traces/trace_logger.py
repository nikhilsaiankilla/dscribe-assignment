import json
from pathlib import Path
from datetime import datetime


class TraceLogger:

    def __init__(self, output_dir: Path = Path("outputs")):
        self.steps = []
        self.output_dir = output_dir
        self.output_dir.mkdir(exist_ok=True, parents=True)

    def log(self, entry: dict):
        entry["timestamp"] = datetime.now().isoformat()
        self.steps.append(entry)

    def save(self):
        path = self.output_dir / "trace.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.steps, f, indent=2)
        print(f"\n[Trace] Saved to {path}")
