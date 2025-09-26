"""Unit tests for the :mod:`inventory.service` module."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from inventory.models import (
    ItemUsageStatus,
    NotFoundError,
    Role,
    TaskStatus,
    TaskUrgency,
    ValidationError,
)
from inventory.service import DEFAULT_TAG_COLOR, InventoryService


@pytest.fixture()
def service() -> InventoryService:
    svc = InventoryService()
    svc.register_user(name="Admin", email="admin@example.com", role=Role.ADMIN)
    return svc


@pytest.fixture()
def manager(service: InventoryService):
    return service.register_user(name="Gestor", email="gestor@example.com", role=Role.MANAGER)


@pytest.fixture()
def operator(service: InventoryService):
    return service.register_user(
        name="Operador", email="operador@example.com", role=Role.OPERATOR
    )


@pytest.fixture()
def category(service: InventoryService):
    return service.create_category(
        name="Hardware",
        description="Equipamentos físicos",
        color="#0ea5e9",
    )


def test_tag_definition_lifecycle_updates_items(service, manager, category):
    urgent = service.create_tag_definition(name="Urgente", color="#ff0000")

    item = service.create_item(
        user=manager,
        name="Notebook", 
        description="Notebook de testes",
        category_id=category.id,
        quantity=1,
        minimum_quantity=0,
        serial_number="NB-001",
        location="Lab",
        acquisition_value=1000.0,
        supplier="Fabricante",
        purchase_date=datetime.utcnow(),
        tags=[urgent],
    )

    updated = service.update_tag_definition(
        tag_id=urgent.id,
        name="Crítico",
        color="#ff8800",
    )

    stored_item = service.get_item(item.id)
    assert [(tag.name, tag.color) for tag in stored_item.tags] == [
        (updated.name, updated.color)
    ]

    service.delete_tag_definition(tag_id=urgent.id)

    assert service.get_item(item.id).tags == []


def test_tag_definition_prevents_duplicate_names(service):
    service.create_tag_definition(name="Backup", color="#22d3ee")

    with pytest.raises(ValidationError):
        service.create_tag_definition(name="backup")


def test_update_category_metadata(service, manager, category):
    network = service.create_category(name="Rede", parent_id=category.id)

    updated = service.update_category(
        user=manager,
        category_id=network.id,
        name="Infraestrutura",
        description="Equipamentos de conectividade",
        color="#f97316",
    )

    assert updated.name == "Infraestrutura"
    assert updated.description == "Equipamentos de conectividade"
    assert updated.color == "#f97316"

    with pytest.raises(ValidationError):
        service.update_category(
            user=manager,
            category_id=category.id,
            parent_id=network.id,
        )


def test_create_item_and_low_stock_notification(service, manager, category):
    item = service.create_item(
        user=manager,
        name="Notebook",
        description="Notebook Dell",
        category_id=category.id,
        quantity=2,
        minimum_quantity=5,
        serial_number="SN123",
        location="Sala 1",
        acquisition_value=5000.0,
        supplier="Dell",
        purchase_date=datetime.utcnow(),
        tags=[("Novo", "#22d3ee"), ("Prioritário", "#f97316")],
    )

    assert item.quantity == 2
    assert item.usage_status is ItemUsageStatus.AVAILABLE
    assert {tag.name.lower(): tag.color for tag in item.tags} == {
        "novo": "#22d3ee",
        "prioritário": "#f97316",
    }
    assert any("estoque crítico" in n.message.lower() for n in service.list_notifications())


def test_register_movement_updates_quantity(service, operator, manager, category):
    item = service.create_item(
        user=manager,
        name="Switch",
        description="Switch 48 portas",
        category_id=category.id,
        quantity=10,
        minimum_quantity=2,
        serial_number="SW-48",
        location="Datacenter",
        acquisition_value=1200.0,
        supplier="Cisco",
        purchase_date=datetime.utcnow(),
    )

    movement = service.register_movement(
        user=operator,
        item_id=item.id,
        quantity=-3,
        movement_type="emprestimo",
        notes="Emprestado para o laboratório",
    )

    updated_item = service.list_items()[0]
    assert movement.quantity == -3
    assert updated_item.quantity == 7


def test_usage_status_updates(service, manager, category):
    item = service.create_item(
        user=manager,
        name="Tablet",
        description="Tablet gráfico",
        category_id=category.id,
        quantity=3,
        minimum_quantity=1,
        serial_number="TAB-001",
        location="Estúdio",
        acquisition_value=3500.0,
        supplier="Wacom",
        purchase_date=datetime.utcnow(),
        usage_status="em uso",
    )

    assert item.usage_status is ItemUsageStatus.IN_USE

    updated = service.update_item(
        user=manager,
        item_id=item.id,
        usage_status="disponivel",
    )

    assert updated.usage_status is ItemUsageStatus.AVAILABLE


def test_report_generation(service, manager, operator, category):
    service.create_item(
        user=manager,
        name="Firewall",
        description="Firewall corporativo",
        category_id=category.id,
        quantity=1,
        minimum_quantity=1,
        serial_number="FW-001",
        location="Datacenter",
        acquisition_value=8000.0,
        supplier="Fortinet",
        purchase_date=datetime.utcnow(),
    )

    report = service.generate_report(user=manager, name="itens_em_alerta")
    assert report.name == "itens_em_alerta"
    assert report.data["itens"]

    with pytest.raises(ValidationError):
        service.generate_report(user=manager, name="desconhecido")


def test_schedule_report(service, manager):
    schedule = service.schedule_report(
        user=manager,
        report_name="estoque_atual",
        recipients=["diretoria@tecfag"],
        cron_expression="0 8 * * 1",
    )

    assert schedule.cron_expression == "0 8 * * 1"
    assert schedule.next_run_at is not None


def test_movements_filtered_by_period(service, manager, operator, category):
    item = service.create_item(
        user=manager,
        name="Servidor",
        description="Servidor de arquivos",
        category_id=category.id,
        quantity=5,
        minimum_quantity=1,
        serial_number="SRV-001",
        location="Sala Servidores",
        acquisition_value=15000.0,
        supplier="HP",
        purchase_date=datetime.utcnow(),
    )

    first = service.register_movement(
        user=operator,
        item_id=item.id,
        quantity=-1,
        movement_type="manutencao",
    )
    service.register_movement(
        user=operator,
        item_id=item.id,
        quantity=1,
        movement_type="retorno",
    )

    start = first.occurred_at - timedelta(seconds=1)
    # Usamos uma janela extremamente curta para evitar incluir a segunda
    # movimentação que ocorre logo em seguida durante o teste.
    end = first.occurred_at + timedelta(microseconds=1)
    filtered = service.list_movements(start=start, end=end)

    assert len(filtered) == 1
    assert filtered[0].id == first.id


def test_list_and_get_users(service):
    users = service.list_users()

    assert len(users) == 1

    fetched = service.get_user(users[0].id)

    assert fetched.email == "admin@example.com"


def test_delete_item_and_audit(service, manager, category):
    item = service.create_item(
        user=manager,
        name="Monitor",
        description="Monitor 27 pol.",
        category_id=category.id,
        quantity=3,
        minimum_quantity=1,
        serial_number="MNTR-123",
        location="Suporte",
        acquisition_value=1500.0,
        supplier="LG",
        purchase_date=datetime.utcnow(),
    )

    service.delete_item(user=manager, item_id=item.id)

    with pytest.raises(NotFoundError):
        service.get_item(item.id)


def test_delete_category_without_dependencies(service, manager):
    orphan = service.create_category(name="Descartados", color="#22d3ee")

    service.delete_category(user=manager, category_id=orphan.id)

    assert orphan.id not in {cat.id for cat in service.list_categories()}


def test_delete_category_with_items_fails(service, manager, category):
    service.create_item(
        user=manager,
        name="Hub USB",
        description="Hub 7 portas",
        category_id=category.id,
        quantity=2,
        minimum_quantity=1,
        serial_number="HUB-001",
        location="Estoque",
        acquisition_value=200.0,
        supplier="Kingston",
        purchase_date=datetime.utcnow(),
    )

    with pytest.raises(ValidationError):
        service.delete_category(user=manager, category_id=category.id)


def test_delete_movement_reverts_stock(service, manager, operator, category):
    item = service.create_item(
        user=manager,
        name="Projetor",
        description="Projetor sala reuniões",
        category_id=category.id,
        quantity=5,
        minimum_quantity=1,
        serial_number="PRJ-01",
        location="Sala 2",
        acquisition_value=2500.0,
        supplier="Epson",
        purchase_date=datetime.utcnow(),
    )

    movement = service.register_movement(
        user=operator,
        item_id=item.id,
        quantity=-2,
        movement_type="emprestimo",
    )

    service.delete_movement(user=manager, movement_id=movement.id)

    updated = service.get_item(item.id)
    assert updated.quantity == 5


def test_create_category_invalid_color(service):
    with pytest.raises(ValidationError):
        service.create_category(name="Impressoras", color="vermelho")


def test_create_item_with_string_tags_uses_default_color(service, manager, category):
    item = service.create_item(
        user=manager,
        name="AP Wi-Fi",
        description="Access point corporativo",
        category_id=category.id,
        quantity=3,
        minimum_quantity=1,
        serial_number="AP-01",
        location="Andar 2",
        acquisition_value=1800.0,
        supplier="Ubiquiti",
        purchase_date=datetime.utcnow(),
        tags=["wireless"],
    )

    assert item.tags[0].color == DEFAULT_TAG_COLOR


def test_string_tags_use_predefined_color_when_available(service, manager, category):
    definition = service.create_tag_definition(name="Suporte", color="#0ea5e9")

    item = service.create_item(
        user=manager,
        name="Telefone VoIP",
        description="Aparelho para a recepção",
        category_id=category.id,
        quantity=2,
        minimum_quantity=1,
        serial_number="VOIP-1",
        location="Recepção",
        acquisition_value=450.0,
        supplier="Cisco",
        purchase_date=datetime.utcnow(),
        tags=["suporte"],
    )

    assert item.tags[0].color == definition.color


def test_task_notifications_flow(service, manager, operator, category):
    item = service.create_item(
        user=manager,
        name="Firewall",
        description="Firewall perimetral",
        category_id=category.id,
        quantity=1,
        minimum_quantity=1,
        serial_number="FW-PRD",
        location="Datacenter",
        acquisition_value=12000.0,
        supplier="Fortinet",
        purchase_date=datetime.utcnow(),
    )

    due_soon = datetime.utcnow() + timedelta(hours=2)
    task = service.create_task(
        user=operator,
        item_id=item.id,
        title="Aplicar patch crítico",
        description="Atualizar firmware do firewall",
        requester_name="Rafael",
        requester_role="Gestor de T.I",
        due_at=due_soon,
        urgency=TaskUrgency.URGENT,
    )

    alerts = [n for n in service.list_notifications() if "Tarefa" in n.message]
    assert alerts
    assert any("vence em breve" in n.message for n in alerts)

    service.update_task(
        user=operator,
        task_id=task.id,
        due_at=datetime.utcnow() - timedelta(hours=1),
    )

    alerts = [n for n in service.list_notifications() if "Tarefa" in n.message]
    assert any("atrasada" in n.message for n in alerts)

    completed = service.update_task(
        user=operator,
        task_id=task.id,
        status=TaskStatus.COMPLETED,
    )

    assert completed.status is TaskStatus.COMPLETED
    assert completed.upcoming_alert_sent is False
    assert completed.overdue_alert_sent is False


def test_task_filters_and_cleanup(service, manager, operator, category):
    item = service.create_item(
        user=manager,
        name="Notebook",
        description="Equipe comercial",
        category_id=category.id,
        quantity=5,
        minimum_quantity=1,
        serial_number="NB-COM-1",
        location="Comercial",
        acquisition_value=6500.0,
        supplier="Dell",
        purchase_date=datetime.utcnow(),
    )

    task = service.create_task(
        user=operator,
        item_id=item.id,
        title="Instalar CRM",
        description="Configurar software",
        requester_name="Tarcisio",
        requester_role="Administrador",
        due_at=datetime.utcnow() + timedelta(days=2),
        urgency=TaskUrgency.MEDIUM_TERM,
    )

    pending = service.list_tasks(status=TaskStatus.PENDING)
    assert {t.id for t in pending} == {task.id}

    with pytest.raises(ValidationError):
        service.update_task(user=operator, task_id=task.id, urgency="desconhecida")

    service.delete_item(user=manager, item_id=item.id)
    assert service.list_tasks() == []
