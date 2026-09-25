import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

NOTE_DIRS = ("10-events", "20-concepts", "30-entities", "40-regulations", "50-maps", "60-outputs")


@pytest.fixture
def tax():
    import taxonomy
    return taxonomy.load_taxonomy()


@pytest.fixture
def tmp_vault(tmp_path):
    for d in NOTE_DIRS:
        (tmp_path / d).mkdir()
    return tmp_path
