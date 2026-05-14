"""Reproducibility package for the modal-test paper dataset.

The original scripts used sibling top-level packages such as ``core`` and
``damping``.  Keeping ``src`` itself on ``sys.path`` preserves those imports
while still allowing public commands such as ``python -m src.tools.build_h5``.
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parent
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
