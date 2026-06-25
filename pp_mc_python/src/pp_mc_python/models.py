"""Domain models.

Mirrors the SharePoint list schemas and the AI Builder JSON output schema
from sections 6.1, 6.2 and 4.3 of the technical documentation.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Category(str, Enum):
    MAINTENANCE = "Maintenance"
    NEW_FEATURE = "New Feature"
    BREAKING_CHANGE = "Breaking Change"
    OTHER = "Other"


class Priority(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class ImpactLevel(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class Status(str, Enum):
    OPEN = "Open"     # action required
    CLOSED = "Closed" # routine, auto-closed


@dataclass
class MCItem:
    """One row from the source MessageCenters SharePoint list (section 6.1)."""
    id: int
    created: datetime
    modified: datetime
    full_message_html: str
    processed: bool = False


@dataclass
class ClassificationResult:
    """Exact JSON contract returned by the AI prompt (section 4.3)."""
    title: str
    category: Category
    priority: Priority
    impact: ImpactLevel
    summary: str
    actions_taken: str
    status: Status

    def action_required(self) -> bool:
        return self.status == Status.OPEN


@dataclass
class AdminListItem:
    """One row written to the target AdminList SharePoint list (section 6.2)."""
    source_id: int
    title: str
    category: Category
    priority: Priority
    impact: ImpactLevel
    summary: str
    actions_taken: str
    status: Status
    created_on_src: Optional[datetime] = None
    modified_on_src: Optional[datetime] = None

    @classmethod
    def from_result(cls, src: MCItem, result: ClassificationResult) -> "AdminListItem":
        return cls(
            source_id=src.id,
            title=result.title,
            category=result.category,
            priority=result.priority,
            impact=result.impact,
            summary=result.summary,
            actions_taken=result.actions_taken,
            status=result.status,
            created_on_src=src.created,
            modified_on_src=src.modified,
        )
