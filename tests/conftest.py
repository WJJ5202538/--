from __future__ import annotations

import os
import tempfile
from pathlib import Path

# Point the app at an isolated runtime directory before it is imported.
_TEST_DATA = Path(tempfile.mkdtemp(prefix="docmark-tests-"))
os.environ["DOCMARK_DATA_DIR"] = str(_TEST_DATA)
