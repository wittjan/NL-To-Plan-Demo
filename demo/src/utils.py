import logging
import os
import sys
import warnings

from src.paths import log_file


def safe_remove(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


# ---- logging -----


def setup_logging():
    warnings.filterwarnings(
        "ignore",
        message="invalid escape sequence",
        category=SyntaxWarning,
    )

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    for handler in list(root.handlers):
        if getattr(handler, "_binder_handler", False):
            root.removeHandler(handler)
            handler.close()

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)-5s] %(name)s  %(message)s", datefmt="%H:%M:%S"
    )

    # file: everything at INFO and above
    file_handler = logging.FileHandler(log_file(), encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    file_handler._binder_handler = True
    root.addHandler(file_handler)

    # stderr: errors only
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.ERROR)
    stderr_handler.setFormatter(formatter)
    stderr_handler._binder_handler = True
    root.addHandler(stderr_handler)

    # silence third-party noise
    for name in (
        "httpx",
        "httpcore",
        "huggingface_hub",
        "faster_whisper",
        "ctranslate2",
        "werkzeug",
        "bitsandbytes",
    ):
        logging.getLogger(name).setLevel(logging.ERROR)

    os.environ.setdefault("USE_HUB_KERNELS", "0")
