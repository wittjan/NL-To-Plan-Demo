import os
from pathlib import Path

DEFAULT_RUN_DIR = Path(__file__).resolve().parents[1] / "run"


def run_dir():
    path = Path(os.environ.get("NLP_RUN_DIR", DEFAULT_RUN_DIR)).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def context_file():
    return str(run_dir() / "world_context.json")


def result_file():
    return str(run_dir() / "plan_result.json")


def log_file():
    return str(run_dir() / "world_setup.log")


def runtime_lock_file():
    return str(run_dir() / ".executor.lock")
