from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import role_required
from accounts.models import ROLE_CHIEF, ROLE_DISPATCHER, ROLE_MASTER, ROLE_RESIDENT, Employee, Resident
from accounts.roles import get_role

from . import services
from .forms import (
    MyTicketsFilterForm,
    NewResidentForm,
    QueueFilterForm,
    ResidentSearchForm,
    TicketCreateForm,
)
from .models import ACTIVE_STATUSES, Photo, Priority, Status, Ticket
from .queries import apply_queue_filters, order_queue

PAGE_SIZE = 20


def _paginate(request, qs):
    return Paginator(qs, PAGE_SIZE).get_page(request.GET.get("page"))


def _query_string(request):
    params = request.GET.copy()
    params.pop("page", None)
    return params.urlencode()


@role_required(ROLE_RESIDENT)
def my_tickets(request):
    form = MyTicketsFilterForm(request.GET or None)
    qs = services.visible_tickets(request.user)
    if form.is_valid():
        if form.cleaned_data["status"]:
            qs = qs.filter(status=form.cleaned_data["status"])
        if form.cleaned_data["q"].strip():
            qs = qs.filter(number__icontains=form.cleaned_data["q"].strip())
    page = _paginate(request, qs.order_by("-created_at"))
    return render(
        request,
        "tickets/my.html",
        {"form": form, "page": page, "qs": _query_string(request)},
    )


@role_required(ROLE_DISPATCHER, ROLE_CHIEF)
def queue(request):
    section = request.user.employee.section if get_role(request.user) == ROLE_CHIEF else None
    form = QueueFilterForm(request.GET or None, section=section)
    qs = services.visible_tickets(request.user)
    if form.is_valid():
        qs = apply_queue_filters(qs, form.cleaned_data)
    page = _paginate(request, order_queue(qs))
    return render(request, "tickets/queue.html", {"form": form, "page": page, "qs": _query_string(request)})


@role_required(ROLE_MASTER)
def tasks(request):
    qs = services.visible_tickets(request.user).filter(status__in=ACTIVE_STATUSES)
    page = _paginate(request, order_queue(qs, overdue_first=True))
    return render(request, "tickets/tasks.html", {"page": page, "qs": _query_string(request)})


def _duplicate_warning(request, resident, category, exclude_pk):
    if (
        Ticket.objects.filter(resident=resident, category=category, status__in=ACTIVE_STATUSES)
        .exclude(pk=exclude_pk)
        .exists()
    ):
        messages.warning(
            request,
            "У вас уже есть активная заявка этой категории. Возможно, это дубль, проверьте список заявок",
        )


@role_required(ROLE_RESIDENT, ROLE_DISPATCHER)
def create(request):
    role = get_role(request.user)
    is_dispatcher = role == ROLE_DISPATCHER
    ctx = {"is_dispatcher": is_dispatcher}
    resident = None
    new_mode = False

    if is_dispatcher:
        new_mode = bool(request.POST.get("new") or request.GET.get("new"))
        search_form = ResidentSearchForm(request.GET or None)
        ctx["search_form"] = search_form
        if search_form.is_valid():
            ctx["found"] = search_form.search()
        resident_id = request.POST.get("resident") or request.GET.get("resident")
        if resident_id and not new_mode:
            resident = get_object_or_404(Resident, pk=resident_id)
        ctx["new_mode"] = new_mode
    else:
        resident = get_object_or_404(Resident, user=request.user)

    show_form = resident is not None or new_mode
    ticket_form = (
        TicketCreateForm(request.POST or None, request.FILES or None, is_dispatcher=is_dispatcher)
        if show_form
        else None
    )
    new_form = NewResidentForm(request.POST or None) if new_mode else None

    if request.method == "POST" and show_form:
        valid = ticket_form.is_valid() and (new_form is None or new_form.is_valid())
        if valid:
            data = ticket_form.cleaned_data
            try:
                with transaction.atomic():
                    if new_mode:
                        resident = Resident.objects.create(**new_form.cleaned_data)
                    ticket = services.create_ticket(
                        request.user,
                        resident,
                        data["category"],
                        data["description"],
                        photos=data["photos"],
                        priority=data.get("priority") or Priority.NORMAL,
                        emergency_requested=bool(data.get("emergency")),
                    )
            except services.TicketError as exc:
                ticket_form.add_error(None, str(exc))
            else:
                hours = data["category"].norm_hours
                messages.success(
                    request,
                    f"Заявка № {ticket.number} зарегистрирована. Нормативный срок выполнения: {hours} ч "
                    "с момента принятия диспетчером",
                )
                if not is_dispatcher:
                    _duplicate_warning(request, resident, data["category"], ticket.pk)
                return redirect("tickets:detail", pk=ticket.pk)

    ctx.update({"resident": resident, "ticket_form": ticket_form, "new_form": new_form})
    return render(request, "tickets/create.html", ctx)


@role_required(ROLE_RESIDENT, ROLE_DISPATCHER, ROLE_CHIEF, ROLE_MASTER)
def detail(request, pk):
    user = request.user
    ticket = get_object_or_404(services.visible_tickets(user), pk=pk)
    role = get_role(user)
    section = user.employee.section if role == ROLE_CHIEF else None
    photos = list(ticket.photos.all())
    master_unavailable = bool(
        ticket.master_id and (not ticket.master.is_active or not ticket.master.user.is_active)
    ) and ticket.status in (Status.ACCEPTED, Status.IN_PROGRESS)
    ctx = {
        "ticket": ticket,
        "actions": services.allowed_actions(user, ticket),
        "photos_before": [p for p in photos if p.kind == Photo.Kind.BEFORE],
        "photos_after": [p for p in photos if p.kind == Photo.Kind.AFTER],
        "history": ticket.history.select_related("changed_by"),
        "masters": services.active_masters(section),
        "priorities": Priority.choices,
        "master_unavailable": master_unavailable and role in (ROLE_DISPATCHER, ROLE_CHIEF),
        "show_phone": role in (ROLE_MASTER, ROLE_DISPATCHER, ROLE_CHIEF),
    }
    return render(request, "tickets/detail.html", ctx)


def _get_master(request, role):
    try:
        master = Employee.objects.get(pk=request.POST.get("master"))
    except (Employee.DoesNotExist, ValueError, TypeError) as exc:
        raise services.TicketError("Выберите мастера") from exc
    if role == ROLE_CHIEF and master.section_id != request.user.employee.section_id:
        raise services.TicketError("Мастер относится к другому участку")
    return master


def _version(request):
    try:
        return int(request.POST.get("version"))
    except (TypeError, ValueError):
        return None


def _perform(request, pk, action):
    """Вызывает сервисную функцию по коду действия; возвращает текст успеха."""
    user, post, version = request.user, request.POST, _version(request)
    role = get_role(user)
    if action == "accept":
        services.accept_ticket(
            user, pk, _get_master(request, role), post.get("priority") or Priority.NORMAL, version
        )
        return "Заявка принята"
    if action == "reject":
        services.reject_ticket(user, pk, post.get("reason"), version)
        return "Заявка отклонена"
    if action == "cancel":
        services.cancel_ticket(user, pk, post.get("comment", ""), version)
        return "Заявка отменена"
    if action == "start":
        services.start_work(user, pk, version)
        return "Заявка взята в работу"
    if action == "done":
        services.complete_work(user, pk, request.FILES.getlist("photos"), post.get("comment", ""), version)
        return "Заявка отмечена выполненной"
    if action == "close":
        services.close_ticket(user, pk, post.get("rating"), post.get("comment", ""), version)
        return "Заявка закрыта, спасибо за оценку"
    if action == "return":
        services.return_to_work(user, pk, post.get("comment", ""), version)
        return "Заявка возвращена в работу"
    if action == "assign":
        services.assign_master(user, pk, _get_master(request, role), post.get("comment", ""), version)
        return "Мастер назначен"
    if action == "priority":
        services.change_priority(user, pk, post.get("priority"), post.get("comment", ""), version)
        return "Приоритет изменён"
    raise Http404


@require_POST
@role_required(ROLE_RESIDENT, ROLE_DISPATCHER, ROLE_CHIEF, ROLE_MASTER)
def action(request, pk, action):
    try:
        message = _perform(request, pk, action)
    except Ticket.DoesNotExist as exc:
        raise Http404 from exc
    except services.TicketError as exc:
        messages.error(request, str(exc))
    except PermissionDenied:
        raise
    else:
        messages.success(request, message)
    return redirect("tickets:detail", pk=pk)


@role_required(ROLE_RESIDENT, ROLE_DISPATCHER, ROLE_CHIEF, ROLE_MASTER)
def photo(request, pk):
    """Файл отдаётся только тем, кто видит заявку (раздел 11 ТЗ)."""
    photo = get_object_or_404(Photo.objects.select_related("ticket"), pk=pk)
    if not services.can_view(request.user, photo.ticket):
        raise Http404
    return FileResponse(photo.file.open("rb"))
