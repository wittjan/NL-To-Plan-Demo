import os
import sys
from pathlib import Path

# Candidates: sibling checkout (dev layout), then the container layout.
_DEFAULT_CANDIDATES = (
    Path(__file__).resolve().parents[3]
    / "cognitive_robot_abstract_machine"
    / "pycram"
    / "demos"
    / "thesis_demo",
    Path("/home/jovyan/libs/cognitive_robot_abstract_machine/pycram/demos/thesis_demo"),
)


def demo_dir():
    """Return the thesis_demo package directory; NLP_DEMO_DIR wins."""
    override = os.environ.get("NLP_DEMO_DIR")
    if override:
        return Path(override)
    for candidate in _DEFAULT_CANDIDATES:
        if candidate.is_dir():
            return candidate
    return _DEFAULT_CANDIDATES[0]


# The package directory's parent makes `import thesis_demo.*` resolve.
_PARENT = str(demo_dir().parent)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)
