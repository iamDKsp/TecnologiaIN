"""Domain models for the TecnologiaIN inventory system."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set


class ItemUsageStatus(str, Enum):
    """Represents whether an item is currently available or in use."""

    AVAILABLE = "available"
    IN_USE = "in_use"

    @property
    def label(self) -> str:
        return "Disponível" if self is ItemUsageStatus.AVAILABLE else "Em uso"


class Role(str, Enum):
    """Supported user roles.

    The ordering also serves as a hierarchy for permission checks.
    """

    ADMIN = "administrador"
    MANAGER = "gerente"
    OPERATOR = "operador"


ROLE_HIERARCHY: Dict[Role, Set[Role]] = {
    Role.ADMIN: {Role.ADMIN, Role.MANAGER, Role.OPERATOR},
    Role.MANAGER: {Role.MANAGER, Role.OPERATOR},
    Role.OPERATOR: {Role.OPERATOR},
}


@dataclass(slots=True)
class User:
    """Represents a system user."""

    id: str
    name: str
    email: str
    role: Role
    mfa_enabled: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True)
class Category:
    """Represents a category or subcategory for inventory items."""

    id: str
    name: str
    parent_id: Optional[str] = None
    description: Optional[str] = None
    color: str = "#6366f1"


@dataclass(slots=True)
class Tag:
    """Visual label associated with an inventory item."""

    name: str
    color: str


@dataclass(slots=True)
class Item:
    """Represents an inventory item."""

    id: str
    name: str
    description: str
    category_id: str
    quantity: int
    minimum_quantity: int
    serial_number: Optional[str]
    location: str
    acquisition_value: float
    supplier: Optional[str]
    purchase_date: Optional[datetime]
    tags: List[Tag] = field(default_factory=list)
    attachments: List[str] = field(default_factory=list)
    usage_status: ItemUsageStatus = ItemUsageStatus.AVAILABLE
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def apply_tags(self, *tags: Tag) -> None:
        lookup = {tag.name.strip().lower(): tag for tag in self.tags}
        for tag in tags:
            key = tag.name.strip().lower()
            lookup[key] = Tag(name=tag.name.strip(), color=tag.color)
        self.tags = list(lookup.values())
        self.updated_at = datetime.utcnow()

    def remove_tags(self, *tags: str) -> None:
        if not tags:
            return
        forbidden = {tag.strip().lower() for tag in tags if tag.strip()}
        if not forbidden:
            return
        self.tags = [tag for tag in self.tags if tag.name.strip().lower() not in forbidden]
        self.updated_at = datetime.utcnow()


@dataclass(slots=True)
class Movement:
    """Represents an inventory movement (entrada/saída)."""

    id: str
    item_id: str
    quantity: int
    movement_type: str
    responsible_id: str
    occurred_at: datetime
    notes: Optional[str] = None


@dataclass(slots=True)
class AuditEntry:
    """Represents a single audit log entry."""

    id: str
    user_id: str
    action: str
    entity: str
    entity_id: str
    payload: Dict[str, object]
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True)
class Notification:
    """Represents a system notification."""

    id: str
    message: str
    severity: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    acknowledged: bool = False


@dataclass(slots=True)
class Report:
    """Represents a generated analytical report."""

    id: str
    name: str
    generated_at: datetime
    parameters: Dict[str, object]
    data: Dict[str, object]


@dataclass(slots=True)
class ScheduledReport:
    """Represents an automated scheduled report."""

    id: str
    report_name: str
    recipients: List[str]
    cron_expression: str
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None


class InventoryError(Exception):
    """Base class for domain specific exceptions."""


class PermissionDenied(InventoryError):
    """Raised when a user does not have permissions for the requested action."""


class NotFoundError(InventoryError):
    """Raised when a requested entity is not found."""


class ValidationError(InventoryError):
    """Raised when an entity fails validation rules."""
