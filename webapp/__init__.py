"""Flask application exposing a simple TecnologiaIN web interface."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from flask import (
    Flask,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from inventory.models import InventoryError, ROLE_HIERARCHY, Role, ValidationError
from inventory.service import InventoryService


def create_app() -> Flask:
    """Application factory configuring routes and demo data."""

    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["SECRET_KEY"] = "tecnologiain-dev"

    service = InventoryService()
    admin = service.register_user(
        name="Tarcisio Pereira",
        email="tarcisio.pereira@tecnologiain",
        role=Role.ADMIN,
        mfa_enabled=True,
    )
    manager = service.register_user(
        name="Rafael Bomfim",
        email="rafael.bomfim@tecnologiain",
        role=Role.MANAGER,
    )
    operator = service.register_user(
        name="Raphael Acosta",
        email="raphael.acosta@tecnologiain",
        role=Role.OPERATOR,
    )

    hardware = service.create_category(
        name="Hardware", description="Servidores, notebooks e periféricos"
    )
    service.create_category(
        name="Software",
        description="Licenças e assinaturas",
    )
    networking = service.create_category(
        name="Rede",
        description="Switches, roteadores e cabos",
        parent_id=hardware.id,
    )

    service.create_item(
        user=admin,
        name="Notebook Dell XPS",
        description="Notebook de desenvolvimento",
        category_id=hardware.id,
        quantity=12,
        minimum_quantity=5,
        serial_number="D-XPS-001",
        location="Escritório Central",
        acquisition_value=8200.0,
        supplier="Dell",
        purchase_date=datetime.utcnow(),
        tags=["desenvolvimento", "prioritario"],
    )
    service.create_item(
        user=admin,
        name="Switch Cisco 48p",
        description="Switch gerenciável para datacenter",
        category_id=networking.id,
        quantity=4,
        minimum_quantity=2,
        serial_number="CISCO-48P-01",
        location="Datacenter",
        acquisition_value=12500.0,
        supplier="Cisco",
        purchase_date=datetime.utcnow(),
        tags=["rede"],
    )

    app.config["inventory_service"] = service

    register_routes(app)
    return app


def register_routes(app: Flask) -> None:
    service: InventoryService = app.config["inventory_service"]

    def _current_user():
        user_id = session.get("user_id")
        if not user_id:
            return None
        try:
            return service.get_user(user_id)
        except InventoryError:
            session.pop("user_id", None)
            return None

    @app.before_request
    def inject_user() -> None:
        g.current_user = _current_user()

    @app.context_processor
    def context() -> dict[str, object]:
        return {
            "current_user": g.get("current_user"),
            "Role": Role,
            "role_hierarchy": ROLE_HIERARCHY,
        }

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            user_id = request.form.get("user_id")
            if user_id:
                try:
                    user = service.get_user(user_id)
                except InventoryError:
                    flash("Usuário inválido", "danger")
                else:
                    session["user_id"] = user.id
                    flash(f"Bem-vindo, {user.name}!", "success")
                    return redirect(url_for("dashboard"))
            else:
                flash("Selecione um usuário para continuar", "warning")
        return render_template("login.html", users=service.list_users())

    @app.route("/logout")
    def logout():
        session.clear()
        flash("Sessão encerrada.", "info")
        return redirect(url_for("login"))

    @app.route("/")
    def dashboard():
        if not g.current_user:
            return redirect(url_for("login"))

        items = service.list_items()
        categories = service.list_categories()
        low_stock = [item for item in items if item.quantity <= item.minimum_quantity]
        notifications = service.list_notifications()[:5]
        movements = service.list_movements()[-5:]
        item_lookup = {item.id: item for item in items}

        return render_template(
            "dashboard.html",
            items=items,
            categories=categories,
            low_stock=low_stock,
            notifications=notifications,
            movements=movements,
            item_lookup=item_lookup,
        )

    @app.route("/categorias", methods=["GET", "POST"])
    def categories():
        if not g.current_user:
            return redirect(url_for("login"))

        if request.method == "POST":
            name = request.form.get("name", "").strip()
            description = request.form.get("description") or None
            parent_id = request.form.get("parent_id") or None
            if name:
                try:
                    service.create_category(name=name, description=description, parent_id=parent_id)
                except ValidationError as exc:
                    flash(str(exc), "danger")
                else:
                    flash("Categoria criada com sucesso!", "success")
                    return redirect(url_for("categories"))
            else:
                flash("Nome da categoria é obrigatório", "warning")

        categories = service.list_categories()
        return render_template("categories.html", categories=categories)

    @app.post("/categorias/<category_id>/remover")
    def remove_category(category_id: str):
        if not g.current_user:
            return redirect(url_for("login"))

        try:
            service.delete_category(user=g.current_user, category_id=category_id)
        except InventoryError as exc:
            flash(str(exc), "danger")
        else:
            flash("Categoria removida com sucesso!", "success")
        return redirect(url_for("categories"))

    @app.route("/itens")
    def items():
        if not g.current_user:
            return redirect(url_for("login"))

        selected_category = request.args.get("categoria") or None
        category_lookup = {c.id: c for c in service.list_categories()}
        items = service.list_items(category_id=selected_category) if selected_category else service.list_items()
        return render_template(
            "items.html",
            items=items,
            categories=category_lookup.values(),
            category_lookup=category_lookup,
            selected_category=selected_category,
        )

    @app.route("/itens/novo", methods=["GET", "POST"])
    def new_item():
        if not g.current_user:
            return redirect(url_for("login"))

        categories = service.list_categories()
        if request.method == "POST":
            form = request.form
            try:
                quantity = int(form.get("quantity", "0"))
                minimum_quantity = int(form.get("minimum_quantity", "0"))
                acquisition_value = float(form.get("acquisition_value", "0"))
            except ValueError:
                flash("Valores numéricos inválidos", "danger")
            else:
                name = form.get("name", "").strip()
                description = form.get("description", "").strip()
                category_id = form.get("category_id", "")
                location = form.get("location", "").strip()
                if not all([name, description, category_id, location]):
                    flash("Preencha todos os campos obrigatórios", "warning")
                    return render_template("item_form.html", categories=categories)
                purchase_date = form.get("purchase_date")
                parsed_date: Optional[datetime] = None
                if purchase_date:
                    try:
                        parsed_date = datetime.strptime(purchase_date, "%Y-%m-%d")
                    except ValueError:
                        flash("Data de compra inválida", "danger")
                        return render_template("item_form.html", categories=categories)
                tags = [tag.strip() for tag in form.get("tags", "").split(",") if tag.strip()]
                attachments = [a.strip() for a in form.get("attachments", "").splitlines() if a.strip()]
                try:
                    service.create_item(
                        user=g.current_user,
                        name=name,
                        description=description,
                        category_id=category_id,
                        quantity=quantity,
                        minimum_quantity=minimum_quantity,
                        serial_number=form.get("serial_number") or None,
                        location=location,
                        acquisition_value=acquisition_value,
                        supplier=form.get("supplier") or None,
                        purchase_date=parsed_date,
                        tags=tags,
                        attachments=attachments,
                    )
                except InventoryError as exc:
                    flash(str(exc), "danger")
                else:
                    flash("Item cadastrado com sucesso!", "success")
                    return redirect(url_for("items"))

        return render_template("item_form.html", categories=categories)

    @app.post("/itens/<item_id>/remover")
    def remove_item(item_id: str):
        if not g.current_user:
            return redirect(url_for("login"))

        selected_category = request.form.get("categoria") or None

        try:
            service.delete_item(user=g.current_user, item_id=item_id)
        except InventoryError as exc:
            flash(str(exc), "danger")
        else:
            flash("Item removido com sucesso!", "success")

        if selected_category:
            return redirect(url_for("items", categoria=selected_category))
        return redirect(url_for("items"))

    @app.route("/movimentacoes", methods=["GET", "POST"])
    def movements():
        if not g.current_user:
            return redirect(url_for("login"))

        items_lookup = {item.id: item for item in service.list_items()}

        if request.method == "POST":
            form = request.form
            try:
                quantity = int(form.get("quantity", "0"))
            except ValueError:
                flash("Quantidade inválida", "danger")
            else:
                direction = form.get("direction", "entrada")
                signed_quantity = quantity if direction == "entrada" else -quantity
                movement_type = form.get("movement_type", direction)
                try:
                    service.register_movement(
                        user=g.current_user,
                        item_id=form.get("item_id", ""),
                        quantity=signed_quantity,
                        movement_type=movement_type,
                        notes=form.get("notes") or None,
                    )
                except InventoryError as exc:
                    flash(str(exc), "danger")
                else:
                    flash("Movimentação registrada", "success")
                    return redirect(url_for("movements"))

        movements = service.list_movements()
        users = {user.id: user for user in service.list_users()}
        return render_template(
            "movements.html",
            movements=movements,
            items_lookup=items_lookup,
            users=users,
        )

    @app.post("/movimentacoes/<movement_id>/remover")
    def remove_movement(movement_id: str):
        if not g.current_user:
            return redirect(url_for("login"))

        try:
            service.delete_movement(user=g.current_user, movement_id=movement_id)
        except InventoryError as exc:
            flash(str(exc), "danger")
        else:
            flash("Movimentação removida com sucesso!", "success")
        return redirect(url_for("movements"))

    @app.route("/alertas")
    def notifications():
        if not g.current_user:
            return redirect(url_for("login"))

        notifications = service.list_notifications()
        return render_template("notifications.html", notifications=notifications)

    @app.route("/auditoria")
    def audit():
        if not g.current_user:
            return redirect(url_for("login"))

        log = service.audit_log()
        users = {user.id: user for user in service.list_users()}
        return render_template("audit.html", log=log, users=users)


__all__ = ["create_app"]
