"""Application service layer implementing the TecnologiaIN use cases."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional, Tuple
from uuid import uuid4

from .models import (
    AuditEntry,
    Category,
    InventoryError,
    Item,
    Movement,
    NotFoundError,
    Notification,
    PermissionDenied,
    Report,
    Role,
    ROLE_HIERARCHY,
    ScheduledReport,
    User,
    ValidationError,
)


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
        self, *, name: str, description: Optional[str] = None, parent_id: Optional[str] = None
    ) -> Category:
        if parent_id and parent_id not in self._categories:
            raise ValidationError("Categoria pai inexistente")

        category = Category(id=str(uuid4()), name=name, parent_id=parent_id, description=description)
        self._categories[category.id] = category
        return category

    def list_categories(self) -> List[Category]:
        return list(self._categories.values())

    def get_category(self, category_id: str) -> Category:
        """Retrieve a category by id."""

        return self._get_category_or_raise(category_id)

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
        tags: Optional[Iterable[str]] = None,
        attachments: Optional[Iterable[str]] = None,
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
        )
        if tags:
            item.apply_tags(*tags)
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
            "status",
        }
        invalid = set(updates) - supported
        if invalid:
            raise ValidationError(f"Campos inválidos para atualização: {', '.join(invalid)}")

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
    ) -> Movement:
        self._require_role(user, Role.OPERATOR)
        if quantity == 0:
            raise ValidationError("Movimentações devem alterar a quantidade")

        item = self._get_item_or_raise(item_id)
        new_quantity = item.quantity + quantity
        if new_quantity < 0:
            raise ValidationError("Quantidade insuficiente em estoque")

        updated_item = replace(item, quantity=new_quantity, updated_at=datetime.utcnow())
        self._items[item_id] = updated_item

        movement = Movement(
            id=str(uuid4()),
            item_id=item_id,
            quantity=quantity,
            movement_type=movement_type,
            responsible_id=user.id,
            occurred_at=datetime.utcnow(),
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
