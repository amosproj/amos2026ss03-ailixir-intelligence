from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_PLAYGROUND_ROOT = Path(__file__).resolve().parent.parent
if str(_PLAYGROUND_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLAYGROUND_ROOT))

from schemas.medical_schema import MEDICAL_SCHEMA  # noqa: E402
from schemas.financial_schema import FINANCIAL_SCHEMA  # noqa: E402


def get_schema(doc_type: str) -> dict[str, Any]:
    if doc_type.lower() == "financial":
        return FINANCIAL_SCHEMA
    return MEDICAL_SCHEMA
