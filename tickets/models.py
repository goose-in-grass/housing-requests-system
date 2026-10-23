import os
import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q


def photo_upload_path(instance, filename):
    """Случайное имя файла на диске (UUID), расширение сохраняется."""
    ext = os.path.splitext(filename)[1].lower()[:5]
    return f"photos/{uuid.uuid4().hex}{ext}"


class Status(models.TextChoices):
    NEW = "new", "Подана"
    ACCEPTED = "accepted", "Принята"
    IN_PROGRESS = "in_progress", "В работе"
    DONE = "done", "Выполнена"
    CLOSED = "closed", "Закрыта"
    REJECTED = "rejected", "Отклонена"
    CANCELLED = "cancelled", "Отменена"


ACTIVE_STATUSES = (Status.NEW, Status.ACCEPTED, Status.IN_PROGRESS, Status.DONE)
FINAL_STATUSES = (Status.CLOSED, Status.REJECTED, Status.CANCELLED)
# Просрочкой не считается статус «Выполнена» (раздел 7 ТЗ).
OVERDUE_STATUSES = (Status.NEW, Status.ACCEPTED, Status.IN_PROGRESS)


class Priority(models.TextChoices):
    NORMAL = "normal", "Обычная"
    EMERGENCY = "emergency", "Аварийная"


class Source(models.TextChoices):
    WEB = "web", "Сайт"
    PHONE = "phone", "Телефон"


class Ticket(models.Model):
    number = models.CharField("Номер", max_length=11, unique=True)
    resident = models.ForeignKey(
        "accounts.Resident", on_delete=models.PROTECT, verbose_name="Жилец", related_name="tickets"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name="Кто создал", related_name="+"
    )
    source = models.CharField("Источник", max_length=10, choices=Source.choices, default=Source.WEB)
    category = models.ForeignKey(
        "directory.Category", on_delete=models.PROTECT, verbose_name="Категория", related_name="tickets"
    )
    # Копия адреса на момент подачи: смена адреса жильца не меняет старые заявки.
    house = models.ForeignKey(
        "directory.House", on_delete=models.PROTECT, verbose_name="Дом", related_name="tickets"
    )
    apartment = models.CharField("Квартира", max_length=10)
    description = models.TextField("Описание", max_length=2000)
    priority = models.CharField("Приоритет", max_length=10, choices=Priority.choices, default=Priority.NORMAL)
    status = models.CharField("Статус", max_length=15, choices=Status.choices, default=Status.NEW)
    master = models.ForeignKey(
        "accounts.Employee",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        verbose_name="Мастер",
        related_name="tickets",
    )
    created_at = models.DateTimeField("Создана", auto_now_add=True)
    updated_at = models.DateTimeField("Изменена", auto_now=True)
    accepted_at = models.DateTimeField("Принята", null=True, blank=True)
    deadline_at = models.DateTimeField("Срок выполнения", null=True, blank=True)
    reject_reason = models.TextField("Причина отказа", max_length=500, blank=True)
    rating = models.PositiveSmallIntegerField(
        "Оценка", null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    rating_comment = models.TextField("Комментарий к оценке", max_length=500, blank=True)
    version = models.PositiveIntegerField("Версия", default=1)

    class Meta:
        verbose_name = "Заявка"
        verbose_name_plural = "Заявки"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["deadline_at"]),
            models.Index(fields=["house", "status"]),
            models.Index(fields=["master", "status"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(rating__isnull=True) | Q(rating__gte=1, rating__lte=5), name="ticket_rating_1_5"
            ),
        ]

    def __str__(self):
        return f"Заявка № {self.number}"


class TicketCounter(models.Model):
    """Счётчик номеров заявок по годам: номер уникален и непрерывен внутри года (FR-C1)."""

    year = models.PositiveSmallIntegerField(primary_key=True)
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Счётчик номеров"
        verbose_name_plural = "Счётчики номеров"


class StatusHistory(models.Model):
    class Event(models.TextChoices):
        STATUS = "status", "Смена статуса"
        ASSIGN = "assign", "Назначение мастера"
        PRIORITY = "priority", "Смена приоритета"
        COMMENT = "comment", "Комментарий"

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="history")
    event = models.CharField("Событие", max_length=10, choices=Event.choices)
    old_status = models.CharField(max_length=15, choices=Status.choices, blank=True)
    new_status = models.CharField(max_length=15, choices=Status.choices, blank=True)
    old_value = models.CharField(max_length=150, blank=True)
    new_value = models.CharField(max_length=150, blank=True)
    comment = models.TextField("Комментарий", max_length=500, blank=True)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Запись истории"
        verbose_name_plural = "История статусов"
        ordering = ["changed_at", "pk"]

    def save(self, *args, **kwargs):
        # Записи истории не редактируются (раздел 5, правило 2).
        if self.pk:
            raise ValueError("Записи истории изменять нельзя")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Записи истории удалять нельзя")


class Photo(models.Model):
    class Kind(models.TextChoices):
        BEFORE = "before", "До"
        AFTER = "after", "После"

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="photos")
    kind = models.CharField("Тип", max_length=10, choices=Kind.choices)
    file = models.ImageField("Файл", upload_to=photo_upload_path)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Фото"
        verbose_name_plural = "Фото"
