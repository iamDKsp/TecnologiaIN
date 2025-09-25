"""Unit tests for the :mod:`inventory.service` module."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from inventory.models import Role, ValidationError
from inventory.service import InventoryService


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
    return service.create_category(name="Hardware", description="Equipamentos físicos")


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
        tags=["novo", "prioritario"],
    )

    assert item.quantity == 2
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
