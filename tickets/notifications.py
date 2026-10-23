"""E-mail-уведомления (раздел 9 ТЗ).

Письмо уходит только после успешной фиксации транзакции; ошибка отправки
пишется в лог и не отменяет смену статуса.
"""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

logger = logging.getLogger(__name__)


def _fmt(dt):
    return timezone.localtime(dt).strftime("%d.%m.%Y %H:%M") if dt else "не назначен"


def _link(ticket):
    base = getattr(settings, "SITE_URL", "http://localhost:8000")
    return base + reverse("tickets:detail", args=[ticket.pk])


def _send(recipients, ticket, status_name, lines):
    recipients = [r for r in recipients if r]
    if not recipients:
        return
    subject = f"Заявка № {ticket.number}: {status_name}"
    body = "\n".join(lines) + f"\n\nАдрес: {ticket.house.address}, кв. {ticket.apartment}\n{_link(ticket)}\n"

    def _do_send():
        try:
            send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, recipients, fail_silently=False)
        except Exception:
            logger.exception("Не удалось отправить письмо по заявке %s", ticket.number)

    transaction.on_commit(_do_send)


def _resident_email(ticket):
    resident = ticket.resident
    if resident.user_id and resident.user.email:
        return resident.user.email
    return resident.email


def ticket_created(ticket):
    _send(
        [_resident_email(ticket)],
        ticket,
        "Подана",
        [f"Заявка № {ticket.number} зарегистрирована.", f"Категория: {ticket.category.name}."],
    )


def ticket_accepted(ticket):
    _send(
        [_resident_email(ticket)],
        ticket,
        "Принята",
        [f"Мастер: {ticket.master.full_name}.", f"Срок выполнения: {_fmt(ticket.deadline_at)}."],
    )


def ticket_rejected(ticket):
    _send([_resident_email(ticket)], ticket, "Отклонена", [f"Причина отказа: {ticket.reject_reason}"])


def ticket_in_progress(ticket):
    _send([_resident_email(ticket)], ticket, "В работе", ["Мастер приступил к работе."])


def ticket_done(ticket):
    _send(
        [_resident_email(ticket)],
        ticket,
        "Выполнена",
        ["Работа выполнена. Подтвердите выполнение и оцените её по ссылке ниже."],
    )


def ticket_closed(ticket):
    _send(
        [_resident_email(ticket)],
        ticket,
        "Закрыта",
        ["Спасибо за обращение!", f"Ваша оценка: {ticket.rating}."],
    )


def master_assigned(ticket):
    master = ticket.master
    _send(
        [master.user.email],
        ticket,
        "назначена вам",
        [f"Категория: {ticket.category.name}.", f"Срок выполнения: {_fmt(ticket.deadline_at)}."],
    )


def returned_to_work(ticket, comment):
    from accounts.models import ROLE_DISPATCHER, Employee

    recipients = []
    if ticket.master_id:
        recipients.append(ticket.master.user.email)
    recipients += list(
        Employee.objects.filter(role=ROLE_DISPATCHER, is_active=True).values_list("user__email", flat=True)
    )
    _send(recipients, ticket, "возвращена в работу", [f"Комментарий жильца: {comment}"])
