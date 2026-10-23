"""Выборки заявок: порядок очереди, фильтры, просрочка (раздел 7 ТЗ)."""

from django.db.models import Case, F, IntegerField, Q, Value, When
from django.utils import timezone

from .models import FINAL_STATUSES, OVERDUE_STATUSES, Priority


def overdue_q(now=None):
    return Q(status__in=OVERDUE_STATUSES, deadline_at__lt=now or timezone.now())


def order_queue(qs, overdue_first=False):
    """Аварийные по сроку, затем обычные по сроку, затем финальные по убыванию изменения.

    Для мастера (overdue_first) просроченные и аварийные идут в самом верху.
    """
    final = Q(status__in=FINAL_STATUSES)
    qs = qs.annotate(
        grp=Case(
            When(final, then=Value(2)),
            When(priority=Priority.EMERGENCY, then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        ),
        sort_deadline=Case(When(final, then=None), default=F("deadline_at")),
        final_updated=Case(When(final, then=F("updated_at")), default=None),
    )
    keys = [
        F("grp").asc(),
        F("sort_deadline").asc(nulls_last=True),
        F("final_updated").desc(nulls_last=True),
        "created_at",
    ]
    if overdue_first:
        qs = qs.annotate(
            top=Case(
                When(
                    overdue_q() | Q(priority=Priority.EMERGENCY, status__in=OVERDUE_STATUSES), then=Value(0)
                ),
                default=Value(1),
                output_field=IntegerField(),
            )
        )
        keys.insert(0, F("top").asc())
    return qs.order_by(*keys)


def apply_queue_filters(qs, data):
    status = data.get("status")
    if status == "active":
        qs = qs.exclude(status__in=FINAL_STATUSES)
    elif status == "overdue":
        qs = qs.filter(overdue_q())
    elif status:
        qs = qs.filter(status=status)
    if data.get("house"):
        qs = qs.filter(house=data["house"])
    if data.get("category"):
        qs = qs.filter(category=data["category"])
    if data.get("priority"):
        qs = qs.filter(priority=data["priority"])
    if data.get("master"):
        qs = qs.filter(master=data["master"])
    q = (data.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(number__icontains=q) | Q(house__address__icontains=q))
    return qs
