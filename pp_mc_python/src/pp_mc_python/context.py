"""FlowContext — the equivalent of Step 2 (Initialize Variables x4).

The Power Automate flow initialises four working variables before any logic
runs. Here they live as a single dataclass that is threaded through every
stage. Each stage mutates exactly the field it is responsible for; nothing
else is touched.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from .models import MCItem, ClassificationResult


@dataclass
class FlowContext:
    source_item: MCItem

    # Working variables from Step 2
    var_clean_message: str = ""
    var_title: str = ""
    var_category: str = ""
    var_status: str = ""

    # Filled later in the pipeline
    classification: Optional[ClassificationResult] = None

    # Bookkeeping
    skipped: bool = False
    skip_reason: str = ""
    error: Optional[BaseException] = None
