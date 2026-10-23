"""Бизнес-логика заявок: статусы, назначение, сроки, история.

Каждая функция сама проверяет права и таблицу переходов и выполняется
в одной транзакции с блокировкой строки заявки (раздел 11 ТЗ).
"""

from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from accounts.models import ROLE_CHIEF, ROLE_DISPATCHER, ROLE_MASTER, ROLE_RESIDENT, Employee
from accounts.roles import get_employee, get_role

from . import notifications
from .models import (
    FINAL_STATUSES,
    Photo,
    Priority,
    Source,
    Status,
    StatusHistory,
    Ticket,
    TicketCounter,
)
from .validators import validate_photos


class TicketError(Exception):
    """Нарушение бизнес-правила; текст показывается пользователю."""


class InvalidTransition(TicketError):
    pass


class StaleTicket(TicketError):
    def __init__(self):
        super().__init__("Заявка уже изменена, обновите страницу")


# (из, в) -> роли, которым разрешён переход (раздел 5 ТЗ).
TRANSITIONS = {
    (Status.NEW, Status.ACCEPTED): {ROLE_DISPATCHER, ROLE_CHIEF},
    (Status.NEW, Status.REJECTED): {ROLE_DISPATCHER, ROLE_CHIEF},
    (Status.NEW, Status.CANCELLED): {ROLE_RESIDENT, ROLE_DISPATCHER, ROLE_CHIEF},
    (Status.ACCEPTED, Status.IN_PROGRESS): {ROLE_MASTER},
    (Status.ACCEPTED, Status.REJECTED): {ROLE_DISPATCHER, ROLE_CHIEF},
    (Status.IN_PROGRESS, Status.DONE): {ROLE_MASTER},
    (Status.DONE, Status.CLOSED): {ROLE_RESIDENT},
    (Status.DONE, Status.IN_PROGRESS): {ROLE_RESIDENT},
}

MIN_REASON = 10


# ---------------------------------------------------------------- доступ


def visible_tickets(user):
    """Заявки, доступные пользователю (раздел 4 ТЗ). Для прочих — пустой набор."""
    qs = Ticket.objects.select_related("category", "house", "master", "resident")
    role = get_role(user)
    if role == ROLE_RESIDENT:
        return qs.filter(resident__user=user)
    if role == ROLE_DISPATCHER:
        return qs
    if role == ROLE_MASTER:
        return qs.filter(master=user.employee)
    if role == ROLE_CHIEF:
        return qs.filter(house__section=user.employee.section)
    return qs.none()


def can_view(user, ticket):
    return visible_tickets(user).filter(pk=ticket.pk).exists()


def allowed_actions(user, ticket):
    """Коды действий, доступных пользователю над заявкой (для кнопок в шаблоне)."""
    role = get_role(user)
    if role is None or not can_view(user, ticket):
        return set()
    actions = set()
    status = ticket.status
    for (src, dst), roles in TRANSITIONS.items():
        if src != status or role not in roles:
            continue
        if role == ROLE_MASTER and ticket.master_id != user.employee.pk:
            continue
        actions.add(dst.value)
    if role in (ROLE_DISPATCHER, ROLE_CHIEF) and status in (Status.ACCEPTED, Status.IN_PROGRESS):
        actions.add("assign")
    if role in (ROLE_DISPATCHER, ROLE_CHIEF) and status not in FINAL_STATUSES:
        actions.add("priority")
    return actions


# ---------------------------------------------------------------- вспомогательное


def _require_role(user, *roles):
    role = get_role(user)
    if role not in roles:
        raise PermissionDenied("Недостаточно прав")
    return role


def _locked_ticket(user, ticket_id, version=None):
    """Заявка под блокировкой строки; чужую заявку пользователь «не видит» (404)."""
    ticket = (
        Ticket.objects.select_for_update().select_related("category", "house", "resident").get(pk=ticket_id)
    )
    if not can_view(user, ticket):
        raise Ticket.DoesNotExist
    if version is not None and ticket.version != version:
        raise StaleTicket
    return ticket


def _check_transition(user, ticket, new_status):
    role = get_role(user)
    allowed = TRANSITIONS.get((Status(ticket.status), new_status))
    if allowed is None:
        raise InvalidTransition("Недопустимый переход статуса")
    if role not in allowed:
        raise PermissionDenied("Недостаточно прав")
    if role == ROLE_MASTER and ticket.master_id != user.employee.pk:
        raise PermissionDenied("Заявка назначена другому мастеру")
    return role


def _clean_text(text, min_len=0, max_len=500, error="Некорректный текст"):
    text = (text or "").strip()
    if len(text) < min_len or len(text) > max_len:
        raise TicketError(error)
    return text


def _history(ticket, user, event, **kwargs):
    return StatusHistory.objects.create(ticket=ticket, event=event, changed_by=user, **kwargs)


def _save(ticket):
    ticket.version += 1
    ticket.save()


def _change_status(ticket, user, new_status, comment=""):
    old = ticket.status
    ticket.status = new_status
    _save(ticket)
    _history(ticket, user, StatusHistory.Event.STATUS, old_status=old, new_status=new_status, comment=comment)


def calc_deadline(category, priority, start):
    hours = category.emergency_norm_hours if priority == Priority.EMERGENCY else category.norm_hours
    return start + timedelta(hours=hours)


def _next_number(year):
    counter, _ = TicketCounter.objects.select_for_update().get_or_create(year=year)
    counter.last_number += 1
    counter.save(update_fields=["last_number"])
    return f"{year}-{counter.last_number:06d}"


def _attach_photos(ticket, user, files, kind):
    for file in files:
        Photo.objects.create(ticket=ticket, kind=kind, file=file, uploaded_by=user)


def _master_label(master):
    return master.full_name if master else ""


# ---------------------------------------------------------------- создание


@transaction.atomic
def create_ticket(user, resident, category, description, photos=(), priority=Priority.NORMAL):
    """Подача заявки жильцом или диспетчером по звонку (FR-R1, FR-D2, FR-C1)."""
    role = _require_role(user, ROLE_RESIDENT, ROLE_DISPATCHER)
    if role == ROLE_RESIDENT:
        if resident.user_id != user.pk:
            raise PermissionDenied("Нельзя подать заявку за другого жильца")
        source = Source.WEB
        # Жилец может отметить «Это авария», решение остаётся за диспетчером.
        priority = Priority.NORMAL
    else:
        source = Source.PHONE
    if not category.is_active:
        raise TicketError("Выберите категорию")
    if not resident.house.is_active:
        raise TicketError("Выберите дом из списка")
    description = _clean_text(description, 10, 2000, "Опишите проблему (от 10 символов)")
    try:
        photos = validate_photos(photos)
    except ValidationError as exc:
        raise TicketError(exc.messages[0]) from exc

    ticket = Ticket.objects.create(
        number=_next_number(timezone.now().year),
        resident=resident,
        created_by=user,
        source=source,
        category=category,
        house=resident.house,
        apartment=resident.apartment,
        description=description,
        priority=priority,
    )
    _attach_photos(ticket, user, photos, Photo.Kind.BEFORE)
    _history(ticket, user, StatusHistory.Event.STATUS, new_status=Status.NEW, comment="Заявка подана")
    notifications.ticket_created(ticket)
    return ticket


# ---------------------------------------------------------------- переходы


@transaction.atomic
def accept_ticket(user, ticket_id, master, priority=Priority.NORMAL, version=None):
    """Подана -> Принята: назначается мастер и приоритет, считается срок."""
    ticket = _locked_ticket(user, ticket_id, version)
    _check_transition(user, ticket, Status.ACCEPTED)
    _validate_master(master)
    now = timezone.now()
    ticket.master = master
    ticket.priority = priority
    ticket.accepted_at = now
    ticket.deadline_at = calc_deadline(ticket.category, priority, now)
    _change_status(ticket, user, Status.ACCEPTED, "Заявка принята")
    _history(
        ticket,
        user,
        StatusHistory.Event.ASSIGN,
        new_value=master.full_name,
        comment="Мастер назначен",
    )
    notifications.ticket_accepted(ticket)
    notifications.master_assigned(ticket)
    return ticket


@transaction.atomic
def reject_ticket(user, ticket_id, reason, version=None):
    ticket = _locked_ticket(user, ticket_id, version)
    _check_transition(user, ticket, Status.REJECTED)
    reason = _clean_text(reason, MIN_REASON, 500, "Укажите причину отказа")
    ticket.reject_reason = reason
    _change_status(ticket, user, Status.REJECTED, reason)
    notifications.ticket_rejected(ticket)
    return ticket


@transaction.atomic
def cancel_ticket(user, ticket_id, comment="", version=None):
    ticket = _locked_ticket(user, ticket_id, version)
    _check_transition(user, ticket, Status.CANCELLED)
    _change_status(ticket, user, Status.CANCELLED, _clean_text(comment, 0, 500))
    return ticket


@transaction.atomic
def start_work(user, ticket_id, version=None):
    ticket = _locked_ticket(user, ticket_id, version)
    _check_transition(user, ticket, Status.IN_PROGRESS)
    _change_status(ticket, user, Status.IN_PROGRESS)
    notifications.ticket_in_progress(ticket)
    return ticket


@transaction.atomic
def complete_work(user, ticket_id, photos, comment="", version=None):
    """В работе -> Выполнена: обязательно фото «после» (FR-M4)."""
    ticket = _locked_ticket(user, ticket_id, version)
    _check_transition(user, ticket, Status.DONE)
    try:
        photos = validate_photos(photos)
    except ValidationError as exc:
        raise TicketError(exc.messages[0]) from exc
    if not photos:
        raise TicketError("Приложите фото «после» выполненной работы")
    comment = _clean_text(comment, 0, 500)
    _attach_photos(ticket, user, photos, Photo.Kind.AFTER)
    _change_status(ticket, user, Status.DONE, comment)
    notifications.ticket_done(ticket)
    return ticket


@transaction.atomic
def close_ticket(user, ticket_id, rating, comment="", version=None):
    """Выполнена -> Закрыта: жилец подтверждает и оценивает (FR-R5)."""
    ticket = _locked_ticket(user, ticket_id, version)
    _check_transition(user, ticket, Status.CLOSED)
    try:
        rating = int(rating)
    except (TypeError, ValueError):
        rating = 0
    if not 1 <= rating <= 5:
        raise TicketError("Поставьте оценку от 1 до 5")
    ticket.rating = rating
    ticket.rating_comment = _clean_text(comment, 0, 500)
    _change_status(ticket, user, Status.CLOSED, f"Оценка: {rating}")
    notifications.ticket_closed(ticket)
    return ticket


@transaction.atomic
def return_to_work(user, ticket_id, comment, version=None):
    """Выполнена -> В работе: жилец не принял работу."""
    ticket = _locked_ticket(user, ticket_id, version)
    _check_transition(user, ticket, Status.IN_PROGRESS)
    comment = _clean_text(comment, 1, 500, "Опишите, почему работа не принята")
    _change_status(ticket, user, Status.IN_PROGRESS, comment)
    notifications.returned_to_work(ticket, comment)
    return ticket


# ---------------------------------------------------------------- назначение, приоритет


def _validate_master(master):
    if master is None or master.role != ROLE_MASTER or not master.is_active:
        raise TicketError("Выберите мастера")


@transaction.atomic
def assign_master(user, ticket_id, master, comment="", version=None):
    """Назначение и смена мастера без смены статуса (правила 3–4 раздела 5)."""
    _require_role(user, ROLE_DISPATCHER, ROLE_CHIEF)
    ticket = _locked_ticket(user, ticket_id, version)
    if ticket.status not in (Status.ACCEPTED, Status.IN_PROGRESS):
        raise InvalidTransition("Мастера можно менять только в статусах «Принята» и «В работе»")
    _validate_master(master)
    if master.pk == ticket.master_id:
        raise TicketError("Этот мастер уже назначен")
    comment = _clean_text(comment, 0, 500)
    if ticket.status == Status.IN_PROGRESS:
        if not comment:
            raise TicketError("При смене мастера в работе нужен комментарий")
    old = _master_label(ticket.master)
    ticket.master = master
    old_status = ticket.status
    if old_status == Status.IN_PROGRESS:
        # Новый мастер видит заявку со статусом «Принята».
        ticket.status = Status.ACCEPTED
    _save(ticket)
    _history(
        ticket, user, StatusHistory.Event.ASSIGN, old_value=old, new_value=master.full_name, comment=comment
    )
    if old_status != ticket.status:
        _history(
            ticket,
            user,
            StatusHistory.Event.STATUS,
            old_status=old_status,
            new_status=ticket.status,
            comment="Смена мастера",
        )
    notifications.master_assigned(ticket)
    return ticket


@transaction.atomic
def change_priority(user, ticket_id, priority, comment="", version=None):
    """Смена приоритета. При повышении до аварийного срок считается от момента изменения."""
    _require_role(user, ROLE_DISPATCHER, ROLE_CHIEF)
    ticket = _locked_ticket(user, ticket_id, version)
    if ticket.status in FINAL_STATUSES:
        raise InvalidTransition("Заявка уже в финальном статусе")
    if priority not in Priority.values:
        raise TicketError("Некорректный приоритет")
    if priority == ticket.priority:
        raise TicketError("Приоритет уже установлен")
    comment = _clean_text(comment, 0, 500)
    old = Priority(ticket.priority).label
    ticket.priority = priority
    note = comment
    if ticket.accepted_at is not None:
        if priority == Priority.EMERGENCY:
            ticket.deadline_at = calc_deadline(ticket.category, priority, timezone.now())
        else:
            ticket.deadline_at = calc_deadline(ticket.category, priority, ticket.accepted_at)
        local = timezone.localtime(ticket.deadline_at).strftime("%d.%m.%Y %H:%M")
        note = f"{comment} Срок пересчитан: {local}".strip()
    _save(ticket)
    _history(
        ticket,
        user,
        StatusHistory.Event.PRIORITY,
        old_value=old,
        new_value=Priority(priority).label,
        comment=note,
    )
    return ticket


def active_masters(section=None):
    """Мастера для выбора; с числом активных заявок (FR-D6)."""
    from django.db.models import Count, Q

    from .models import OVERDUE_STATUSES

    qs = Employee.objects.filter(role=ROLE_MASTER, is_active=True, user__is_active=True)
    if section is not None:
        qs = qs.filter(section=section)
    return qs.annotate(
        active_count=Count("tickets", filter=Q(tickets__status__in=OVERDUE_STATUSES))
    ).order_by("full_name")


__all__ = [
    "InvalidTransition",
    "StaleTicket",
    "TicketError",
    "accept_ticket",
    "active_masters",
    "allowed_actions",
    "assign_master",
    "cancel_ticket",
    "can_view",
    "change_priority",
    "close_ticket",
    "complete_work",
    "create_ticket",
    "get_employee",
    "reject_ticket",
    "return_to_work",
    "start_work",
    "visible_tickets",
]
