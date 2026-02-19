from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class QueueItem:
    raw_value: str
    source_kind: str
    display_label: str | None = None


@dataclass
class ItemRunResult:
    queue_index: int
    queue_total: int
    source_kind: str
    source_path: str
    model_name: str
    compute_device: str
    output_format: str
    run_policy: str
    result: str = "pending"
    output_path: str | None = None
    error: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class BatchRunSummary:
    total_items: int
    success_items: int
    failed_items: int
    run_policy: str
    stopped_on_error: bool
    pending_items: int
    total_seconds: float
