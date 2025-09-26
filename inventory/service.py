"""Application service layer implementing the TecnologiaIN use cases."""

from __future__ import annotations

from collections import defaultdict
import re
import unicodedata
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional, Tuple, Union
from uuid import uuid4

from .models import (
    AuditEntry,
    Category,
    InventoryError,
    Item,
    ItemUsageStatus,
    Movement,
    NotFoundError,
    Notification,
    PermissionDenied,
    Report,
    Role,
    ROLE_HIERARCHY,
    Tag,
    ScheduledReport,
    User,
    ValidationError,
)


HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
DEFAULT_CATEGORY_COLOR = "#6366f1"
DEFAULT_TAG_COLOR = "#14b8a6"

TagInput = Union[Tag, Tuple[str, str], Dict[str, str], str]
UsageStatusInput = Union[ItemUsageStatus, str, None]

_UNSET = object()


class InventoryService:
    """Facade exposing the main use cases of the inventory system."""

    def __init__(self) -> None:
        self._items: Dict[str, Item] = {}
        self._categories: Dict[str, Category] = {}
        self._users: Dict[str, User] = {}
        self._movements: Dict[str, Movement] = {}
        self._notifications: Dict[str, Notification] = {}
        self._audit_log: List[AuditEntry] = []
        self._scheduled_reports: Dict[str, ScheduledReport] = {}
        self._report_history: Dict[str, List[Report]] = defaultdict(list)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _require_role(self, user: User, minimum: Role) -> None:
        allowed = ROLE_HIERARCHY[user.role]
        if minimum not in allowed:
            raise PermissionDenied(
                f"Usuário {user.email} não possui permissão para esta operação."
            )

    def _append_audit(
        self,
        *,
        user: User,
        action: str,
        entity: str,
        entity_id: str,
        payload: Optional[Dict[str, object]] = None,
    ) -> None:
        entry = AuditEntry(
            id=str(uuid4()),
            user_id=user.id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            payload=payload or {},
        )
        self._audit_log.append(entry)

    def _emit_notification(self, message: str, severity: str = "info") -> Notification:
        notification = Notification(id=str(uuid4()), message=message, severity=severity)
        self._notifications[notification.id] = notification
        return notification

    def _coerce_usage_status(self, status: UsageStatusInput) -> ItemUsageStatus:
        if status is None:
            return ItemUsageStatus.AVAILABLE
        if isinstance(status, ItemUsageStatus):
            return status

        normalized = unicodedata.normalize("NFD", str(status))
        normalized = normalized.encode("ascii", "ignore").decode("ascii")
        normalized = normalized.strip().lower().replace(" ", "_")

        mapping = {
            "available": ItemUsageStatus.AVAILABLE,
            "disponivel": ItemUsageStatus.AVAILABLE,
            "em_uso": ItemUsageStatus.IN_USE,
            "emuso": ItemUsageStatus.IN_USE,
            "in_use": ItemUsageStatus.IN_USE,
        }

        if normalized in mapping:
            return mapping[normalized]

        raise ValidationError("Status de uso inválido para o item")

    def _normalize_hex_color(self, color: Optional[str], *, default: str) -> str:
        if not color:
            return default
        candidate = color.strip()
        if not HEX_COLOR_RE.fullmatch(candidate):
            raise ValidationError("Cor inválida. Use o formato hexadecimal #RRGGBB")
        return candidate.lower()

    def _coerce_tag(self, raw: TagInput) -> Tag:
        if isinstance(raw, Tag):
            name = raw.name.strip()
            if not name:
                raise ValidationError("Nome da tag é obrigatório")
            color = self._normalize_hex_color(raw.color, default=DEFAULT_TAG_COLOR)
            return Tag(name=name, color=color)

        if isinstance(raw, tuple) and len(raw) == 2:
            name, color = raw
        elif isinstance(raw, dict):
            name = raw.get("name") or raw.get("label")
            color = raw.get("color")
        elif isinstance(raw, str):
            name = raw
            color = DEFAULT_TAG_COLOR
        else:  # pragma: no cover - defensive branch
            raise ValidationError("Formato de tag inválido")

        if not name or not str(name).strip():
            raise ValidationError("Nome da tag é obrigatório")

        normalized_name = str(name).strip()
        normalized_color = self._normalize_hex_color(str(color) if color is not None else None, default=DEFAULT_TAG_COLOR)
        return Tag(name=normalized_name, color=normalized_color)

    def _get_category_or_raise(self, category_id: str) -> Category:
        try:
            return self._categories[category_id]
        except KeyError as exc:  # pragma: no cover - defensive branch
            raise NotFoundError("Categoria não encontrada") from exc

    def _get_item_or_raise(self, item_id: str) -> Item:
        try:
            return self._items[item_id]
        except KeyError as exc:  # pragma: no cover - defensive branch
            raise NotFoundError("Item não encontrado") from exc

    def _get_user_or_raise(self, user_id: str) -> User:
        try:
            return self._users[user_id]
        except KeyError as exc:  # pragma: no cover - defensive branch
            raise NotFoundError("Usuário não encontrado") from exc

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------
    def register_user(
        self, *, name: str, email: str, role: Role, mfa_enabled: bool = False
    ) -> User:
        if email in {user.email for user in self._users.values()}:
            raise ValidationError("Já existe um usuário registrado com este e-mail")

        user = User(id=str(uuid4()), name=name, email=email, role=role, mfa_enabled=mfa_enabled)
        self._users[user.id] = user
        return user

    def enable_mfa(self, *, user_id: str) -> User:
        user = self._get_user_or_raise(user_id)
        updated = replace(user, mfa_enabled=True)
        self._users[user_id] = updated
        return updated

    def list_users(self) -> List[User]:
        """Return all registered users."""

        return list(self._users.values())

    def get_user(self, user_id: str) -> User:
        """Retrieve a user by id, raising :class:`NotFoundError` when absent."""

        return self._get_user_or_raise(user_id)

    # ------------------------------------------------------------------
    # Categories
    # ------------------------------------------------------------------
    def create_category(
        self,
        *,
        name: str,
        description: Optional[str] = None,
        parent_id: Optional[str] = None,
        color: Optional[str] = None,
    ) -> Category:
        if parent_id and parent_id not in self._categories:
            raise ValidationError("Categoria pai inexistente")

        normalized_color = self._normalize_hex_color(color, default=DEFAULT_CATEGORY_COLOR)
        category = Category(
            id=str(uuid4()),
            name=name,
            parent_id=parent_id,
            description=description,
            color=normalized_color,
        )
        self._categories[category.id] = category
        return category

    def update_category(
        self,
        *,
        user: User,
        category_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        parent_id: object = _UNSET,
        color: Optional[str] = None,
    ) -> Category:
        """Update a category's basic metadata."""

        self._require_role(user, Role.MANAGER)
        category = self._get_category_or_raise(category_id)

        parent_specified = parent_id is not _UNSET
        normalized_parent: Optional[str] = category.parent_id
        if parent_specified:
            candidate: Optional[str]
            if parent_id in (None, ""):
                candidate = None
            else:
                candidate = str(parent_id)
                if candidate not in self._categories:
                    raise ValidationError("Categoria pai inexistente")
                if candidate == category_id:
                    raise ValidationError("Uma categoria não pode ser pai dela mesma")
                ancestor = self._categories[candidate]
                while ancestor.parent_id is not None:
                    if ancestor.parent_id == category_id:
                        raise ValidationError("A relação entre categorias criaria um ciclo")
                    ancestor = self._categories[ancestor.parent_id]
            normalized_parent = candidate

        updates: Dict[str, object] = {}
        if name is not None:
            updates["name"] = name
        if description is not None:
            updates["description"] = description
        if parent_specified and normalized_parent != category.parent_id:
            updates["parent_id"] = normalized_parent
        if color is not None:
            updates["color"] = self._normalize_hex_color(color, default=category.color)

        if not updates:
            return category

        updated = replace(category, **updates)
        self._categories[category_id] = updated
        self._append_audit(
            user=user,
            action="atualizar_categoria",
            entity="category",
            entity_id=category_id,
            payload=updates,
        )
        return updated

    def list_categories(self) -> List[Category]:
        return list(self._categories.values())

    def get_category(self, category_id: str) -> Category:
        """Retrieve a category by id."""

        return self._get_category_or_raise(category_id)

    def delete_category(self, *, user: User, category_id: str) -> None:
        """Remove a category when it has no dependencies."""

        self._require_role(user, Role.MANAGER)
        category = self._get_category_or_raise(category_id)

        if any(cat.parent_id == category_id for cat in self._categories.values()):
            raise ValidationError("Não é possível remover uma categoria com subcategorias associadas")
        if any(item.category_id == category_id for item in self._items.values()):
            raise ValidationError("Não é possível remover uma categoria com itens associados")

        del self._categories[category_id]
        self._append_audit(
            user=user,
            action="remover_categoria",
            entity="category",
            entity_id=category.id,
            payload={"name": category.name},
        )

    # ------------------------------------------------------------------
    # Items
    # ------------------------------------------------------------------
    def create_item(
        self,
        *,
        user: User,
        name: str,
        description: str,
        category_id: str,
        quantity: int,
        minimum_quantity: int,
        serial_number: Optional[str],
        location: str,
        acquisition_value: float,
        supplier: Optional[str],
        purchase_date: Optional[datetime],
        tags: Optional[Iterable[TagInput]] = None,
        attachments: Optional[Iterable[str]] = None,
        usage_status: UsageStatusInput = None,
    ) -> Item:
        self._require_role(user, Role.MANAGER)
        self._get_category_or_raise(category_id)

        if quantity < 0 or minimum_quantity < 0:
            raise ValidationError("Quantidade e mínimo devem ser positivos")

        item = Item(
            id=str(uuid4()),
            name=name,
            description=description,
            category_id=category_id,
            quantity=quantity,
            minimum_quantity=minimum_quantity,
            serial_number=serial_number,
            location=location,
            acquisition_value=acquisition_value,
            supplier=supplier,
            purchase_date=purchase_date,
            usage_status=self._coerce_usage_status(usage_status),
        )
        if tags:
            coerced = [self._coerce_tag(tag) for tag in tags]
            item.apply_tags(*coerced)
        if attachments:
            item.attachments.extend(attachments)

        self._items[item.id] = item
        self._append_audit(
            user=user,
            action="criar_item",
            entity="item",
            entity_id=item.id,
            payload={"name": name, "quantity": quantity},
        )
        if item.quantity <= item.minimum_quantity:
            self._emit_notification(
                f"Estoque crítico para {item.name}: {item.quantity} unidades.", severity="warning"
            )
        return item

    def update_item(self, *, user: User, item_id: str, **updates: object) -> Item:
        self._require_role(user, Role.MANAGER)
        item = self._get_item_or_raise(item_id)

        supported = {
            "name",
            "description",
            "category_id",
            "quantity",
            "minimum_quantity",
            "serial_number",
            "location",
            "acquisition_value",
            "supplier",
            "purchase_date",
            "usage_status",
            "tags",
            "attachments",
        }
        invalid = set(updates) - supported
        if invalid:
            raise ValidationError(f"Campos inválidos para atualização: {', '.join(invalid)}")

        if "usage_status" in updates:
            updates["usage_status"] = self._coerce_usage_status(updates["usage_status"])

        if "tags" in updates:
            raw_tags = updates["tags"]
            coerced_tags = [] if raw_tags is None else [self._coerce_tag(tag) for tag in raw_tags]
            updates["tags"] = coerced_tags

        if "attachments" in updates and updates["attachments"] is not None:
            updates["attachments"] = list(updates["attachments"])

        updated = replace(item, **updates, updated_at=datetime.utcnow())
        self._items[item_id] = updated
        self._append_audit(
            user=user,
            action="atualizar_item",
            entity="item",
            entity_id=item_id,
            payload=updates,
        )
        if updated.quantity <= updated.minimum_quantity:
            self._emit_notification(
                f"Estoque crítico para {updated.name}: {updated.quantity} unidades.", severity="warning"
            )
        return updated

    def remove_item(self, *, user: User, item_id: str, reason: str) -> None:
        self._require_role(user, Role.MANAGER)
        item = self._get_item_or_raise(item_id)
        del self._items[item_id]
        self._append_audit(
            user=user,
            action="remover_item",
            entity="item",
            entity_id=item_id,
            payload={"reason": reason},
        )
        self._emit_notification(
            f"Item removido do inventário: {item.name} ({reason}).", severity="info"
        )

    def list_items(self, *, category_id: Optional[str] = None) -> List[Item]:
        if category_id:
            return [item for item in self._items.values() if item.category_id == category_id]
        return list(self._items.values())

    def get_item(self, item_id: str) -> Item:
        """Retrieve an item by id."""

        return self._get_item_or_raise(item_id)

    def delete_item(self, *, user: User, item_id: str) -> None:
        """Remove an item from the catalog."""

        self._require_role(user, Role.MANAGER)
        item = self._get_item_or_raise(item_id)

        del self._items[item_id]
        self._append_audit(
            user=user,
            action="remover_item",
            entity="item",
            entity_id=item.id,
            payload={"name": item.name},
        )

    # ------------------------------------------------------------------
    # Movements
    # ------------------------------------------------------------------
    def register_movement(
        self,
        *,
        user: User,
        item_id: str,
        quantity: int,
        movement_type: str,
        notes: Optional[str] = None,
        occurred_at: Optional[datetime] = None,
    ) -> Movement:
        self._require_role(user, Role.OPERATOR)
        if quantity == 0:
            raise ValidationError("Movimentações devem alterar a quantidade")

        item = self._get_item_or_raise(item_id)
        new_quantity = item.quantity + quantity
        if new_quantity < 0:
            raise ValidationError("Quantidade insuficiente em estoque")

        timestamp = occurred_at or datetime.utcnow()
        updated_item = replace(item, quantity=new_quantity, updated_at=timestamp)
        self._items[item_id] = updated_item

        movement = Movement(
            id=str(uuid4()),
            item_id=item_id,
            quantity=quantity,
            movement_type=movement_type,
            responsible_id=user.id,
            occurred_at=timestamp,
            notes=notes,
        )
        self._movements[movement.id] = movement
        self._append_audit(
            user=user,
            action="movimentar_item",
            entity="movement",
            entity_id=movement.id,
            payload={
                "item_id": item_id,
                "quantity": quantity,
                "movement_type": movement_type,
            },
        )

        if updated_item.quantity <= updated_item.minimum_quantity:
            self._emit_notification(
                f"Estoque crítico para {updated_item.name}: {updated_item.quantity} unidades.",
                severity="warning",
            )
        return movement

    def list_movements(
        self,
        *,
        item_id: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> List[Movement]:
        movements = list(self._movements.values())
        if item_id:
            movements = [m for m in movements if m.item_id == item_id]
        if start:
            movements = [m for m in movements if m.occurred_at >= start]
        if end:
            movements = [m for m in movements if m.occurred_at <= end]
        movements.sort(key=lambda m: m.occurred_at)
        return movements

    def delete_movement(self, *, user: User, movement_id: str) -> None:
        """Remove a movement and revert its stock impact."""

        self._require_role(user, Role.MANAGER)
        movement = self._movements.get(movement_id)
        if not movement:
            raise NotFoundError("Movimentação não encontrada")

        item = self._get_item_or_raise(movement.item_id)
        reverted_quantity = item.quantity - movement.quantity
        if reverted_quantity < 0:
            raise ValidationError(
                "Não é possível remover a movimentação pois resultaria em estoque negativo"
            )

        updated_item = replace(item, quantity=reverted_quantity, updated_at=datetime.utcnow())
        self._items[item.id] = updated_item
        del self._movements[movement_id]

        self._append_audit(
            user=user,
            action="remover_movimentacao",
            entity="movement",
            entity_id=movement.id,
            payload={"item_id": movement.item_id, "quantity": movement.quantity},
        )

    # ------------------------------------------------------------------
    # Notifications & alerts
    # ------------------------------------------------------------------
    def list_notifications(self, *, severity: Optional[str] = None) -> List[Notification]:
        notifications = list(self._notifications.values())
        if severity:
            notifications = [n for n in notifications if n.severity == severity]
        notifications.sort(key=lambda n: n.created_at, reverse=True)
        return notifications

    def acknowledge_notification(self, notification_id: str) -> Notification:
        notification = self._notifications.get(notification_id)
        if not notification:
            raise NotFoundError("Notificação não encontrada")
        acknowledged = replace(notification, acknowledged=True)
        self._notifications[notification_id] = acknowledged
        return acknowledged

    def low_stock_items(self) -> List[Tuple[Item, int]]:
        return [
            (item, item.minimum_quantity)
            for item in self._items.values()
            if item.quantity <= item.minimum_quantity
        ]

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------
    def generate_report(
        self, *, user: User, name: str, parameters: Optional[Dict[str, object]] = None
    ) -> Report:
        self._require_role(user, Role.MANAGER)
        parameters = parameters or {}

        if name == "estoque_atual":
            data = {
                "itens": [
                    {
                        "id": item.id,
                        "nome": item.name,
                        "quantidade": item.quantity,
                        "minimo": item.minimum_quantity,
                        "localizacao": item.location,
                    }
                    for item in self._items.values()
                ]
            }
        elif name == "itens_em_alerta":
            data = {
                "itens": [
                    {
                        "id": item.id,
                        "nome": item.name,
                        "quantidade": item.quantity,
                        "minimo": item.minimum_quantity,
                    }
                    for item in self._items.values()
                    if item.quantity <= item.minimum_quantity
                ]
            }
        elif name == "movimentacoes":
            period_start = parameters.get("inicio")
            period_end = parameters.get("fim")
            movements = self.list_movements(start=period_start, end=period_end)
            data = {
                "movimentacoes": [
                    {
                        "id": movement.id,
                        "item_id": movement.item_id,
                        "quantidade": movement.quantity,
                        "tipo": movement.movement_type,
                        "quando": movement.occurred_at.isoformat(),
                    }
                    for movement in movements
                ]
            }
        else:
            raise ValidationError("Tipo de relatório desconhecido")

        report = Report(
            id=str(uuid4()),
            name=name,
            generated_at=datetime.utcnow(),
            parameters=parameters,
            data=data,
        )
        self._report_history[name].append(report)
        self._append_audit(
            user=user,
            action="gerar_relatorio",
            entity="report",
            entity_id=report.id,
            payload={"name": name},
        )
        return report

    def schedule_report(
        self,
        *,
        user: User,
        report_name: str,
        recipients: List[str],
        cron_expression: str,
    ) -> ScheduledReport:
        self._require_role(user, Role.MANAGER)
        schedule = ScheduledReport(
            id=str(uuid4()),
            report_name=report_name,
            recipients=recipients,
            cron_expression=cron_expression,
            next_run_at=datetime.utcnow() + timedelta(hours=1),
        )
        self._scheduled_reports[schedule.id] = schedule
        self._append_audit(
            user=user,
            action="agendar_relatorio",
            entity="scheduled_report",
            entity_id=schedule.id,
            payload={"report": report_name, "cron": cron_expression},
        )
        return schedule

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------
    def audit_log(self, *, limit: Optional[int] = None) -> List[AuditEntry]:
        log = list(self._audit_log)
        log.sort(key=lambda entry: entry.created_at, reverse=True)
        if limit:
            return log[:limit]
        return log

    # ------------------------------------------------------------------
    # Integrations (mocked)
    # ------------------------------------------------------------------
    def emit_webhook(self, *, event: str, payload: Dict[str, object]) -> str:
        """Registers an outbound webhook event.

        In a real implementation this would enqueue an asynchronous task that
        performs the actual HTTP call. For now we simply generate an ID to
        demonstrate the integration workflow.
        """

        webhook_id = str(uuid4())
        self._append_audit(
            user=self._system_user(),
            action="emitir_webhook",
            entity="webhook",
            entity_id=webhook_id,
            payload={"event": event, **payload},
        )
        return webhook_id

    # ------------------------------------------------------------------
    # Internal utilities
    # ------------------------------------------------------------------
    def _system_user(self) -> User:
        """Returns a synthetic system user for automated actions."""

        system_user = User(id="system", name="Sistema", email="system@tecfag", role=Role.ADMIN)
        if system_user.id not in self._users:
            self._users[system_user.id] = system_user
        return system_user
