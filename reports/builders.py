"""Расчёт отчётов начальника участка (раздел 9 ТЗ). Все выборки ограничены участком."""

from collections import defaultdict
from datetime import datetime, time

from django.db.models import Count
from django.utils import timezone

from accounts.models import ROLE_MASTER, Employee
from directory.models import Category, House
from tickets.models import OVERDUE_STATUSES, Status, StatusHistory, Ticket
from tickets.queries import overdue_q

EXCLUDED = (Status.CANCELLED, Status.REJECTED)

REPORTS = {
    "houses": "Заявки по домам и категориям",
    "dynamics": "Динамика заявок по месяцам",
    "masters": "Работа мастеров",
    "overdue": "Просроченные заявки",
}


def _aware(day, end=False):
    return timezone.make_aware(datetime.combine(day, time.max if end else time.min))


def _base(section, f):
    qs = Ticket.objects.filter(house__section=section).select_related("category", "house", "master")
    if f.get("date_from"):
        qs = qs.filter(created_at__gte=_aware(f["date_from"]))
    if f.get("date_to"):
        qs = qs.filter(created_at__lte=_aware(f["date_to"], end=True))
    if f.get("house"):
        qs = qs.filter(house=f["house"])
    if f.get("category"):
        qs = qs.filter(category=f["category"])
    return qs


def _fmt_dt(dt):
    return timezone.localtime(dt).strftime("%d.%m.%Y %H:%M")


def houses_report(section, f):
    """Дома × категории; отклонённые и отменённые вынесены в отдельный столбец."""
    qs = _base(section, f)
    categories = list(Category.objects.order_by("name"))
    if f.get("category"):
        categories = [f["category"]]
    houses = list(House.objects.filter(section=section).order_by("address"))
    if f.get("house"):
        houses = [f["house"]]
    counts = defaultdict(int)
    dropped = defaultdict(int)
    for row in qs.values("house_id", "category_id", "status").annotate(n=Count("id")):
        if row["status"] in EXCLUDED:
            dropped[row["house_id"]] += row["n"]
        else:
            counts[(row["house_id"], row["category_id"])] += row["n"]
    headers = ["Дом", *[c.name for c in categories], "Итого", "Отклонены и отменены"]
    rows = []
    totals = [0] * len(categories)
    for h in houses:
        values = [counts[(h.pk, c.pk)] for c in categories]
        rows.append([h.address, *values, sum(values), dropped[h.pk]])
        totals = [t + v for t, v in zip(totals, values, strict=True)]
    rows.append(["Итого", *totals, sum(totals), sum(dropped[h.pk] for h in houses)])
    chart = {
        "type": "bar",
        "labels": [r[0] for r in rows[:-1]],
        "datasets": [{"label": "Заявок", "data": [r[-2] for r in rows[:-1]]}],
    }
    return {"headers": headers, "rows": rows, "chart": chart, "total_row": True}


def dynamics_report(section, f):
    qs = _base(section, f).exclude(status__in=EXCLUDED)
    submitted = defaultdict(int)
    for created_at in qs.values_list("created_at", flat=True):
        d = timezone.localtime(created_at)
        submitted[(d.year, d.month)] += 1
    closed = defaultdict(int)
    history = StatusHistory.objects.filter(ticket__in=qs, event="status", new_status=Status.CLOSED)
    for entry in history:
        d = timezone.localtime(entry.changed_at)
        closed[(d.year, d.month)] += 1
    months = sorted(set(submitted) | set(closed))
    rows = [[f"{m:02d}.{y}", submitted[(y, m)], closed[(y, m)]] for y, m in months]
    chart = {
        "type": "line",
        "labels": [r[0] for r in rows],
        "datasets": [
            {"label": "Подано", "data": [r[1] for r in rows]},
            {"label": "Закрыто", "data": [r[2] for r in rows]},
        ],
    }
    return {"headers": ["Месяц", "Подано", "Закрыто"], "rows": rows, "chart": chart}


def masters_report(section, f):
    qs = _base(section, f).exclude(status__in=EXCLUDED).filter(master__isnull=False)
    if f.get("master"):
        qs = qs.filter(master=f["master"])
    masters = Employee.objects.filter(role=ROLE_MASTER, section=section)
    if f.get("master"):
        masters = masters.filter(pk=f["master"].pk)
    done_at = {}
    for entry in StatusHistory.objects.filter(ticket__in=qs, event="status", new_status=Status.DONE).order_by(
        "changed_at"
    ):
        done_at[entry.ticket_id] = entry.changed_at  # берётся последнее выполнение
    now = timezone.now()
    stats = {m.pk: {"assigned": 0, "done": 0, "overdue": 0, "hours": [], "ratings": []} for m in masters}
    for t in qs:
        s = stats.get(t.master_id)
        if s is None:
            continue
        s["assigned"] += 1
        finished = done_at.get(t.pk)
        if finished is not None:
            s["done"] += 1
            if t.accepted_at:
                s["hours"].append((finished - t.accepted_at).total_seconds() / 3600)
            if t.deadline_at and finished > t.deadline_at:
                s["overdue"] += 1
        elif t.status in OVERDUE_STATUSES and t.deadline_at and now > t.deadline_at:
            s["overdue"] += 1
        if t.rating:
            s["ratings"].append(t.rating)
    rows = []
    for m in masters.order_by("full_name"):
        s = stats[m.pk]
        avg_h = round(sum(s["hours"]) / len(s["hours"]), 1) if s["hours"] else "—"
        avg_r = round(sum(s["ratings"]) / len(s["ratings"]), 2) if s["ratings"] else "—"
        rows.append([m.full_name, s["assigned"], s["done"], s["overdue"], avg_h, avg_r])
    headers = ["Мастер", "Назначено", "Выполнено", "Просрочено", "Среднее время, ч", "Средняя оценка"]
    return {"headers": headers, "rows": rows}


def overdue_report(section, f):
    qs = (
        Ticket.objects.filter(house__section=section)
        .filter(overdue_q())
        .select_related("category", "house", "master")
    )
    if f.get("house"):
        qs = qs.filter(house=f["house"])
    if f.get("category"):
        qs = qs.filter(category=f["category"])
    if f.get("master"):
        qs = qs.filter(master=f["master"])
    now = timezone.now()
    rows = [
        [
            t.number,
            f"{t.house.address}, кв. {t.apartment}",
            t.category.name,
            t.master.full_name if t.master else "—",
            _fmt_dt(t.deadline_at),
            round((now - t.deadline_at).total_seconds() / 3600, 1),
        ]
        for t in qs.order_by("deadline_at")
    ]
    headers = ["Номер", "Адрес", "Категория", "Мастер", "Срок", "Просрочена на, ч"]
    return {"headers": headers, "rows": rows}


BUILDERS = {
    "houses": houses_report,
    "dynamics": dynamics_report,
    "masters": masters_report,
    "overdue": overdue_report,
}
