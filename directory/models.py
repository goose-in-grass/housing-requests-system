from django.db import models
from django.db.models import Q


class Section(models.Model):
    name = models.CharField("Название", max_length=100, unique=True)

    class Meta:
        verbose_name = "Участок"
        verbose_name_plural = "Участки"

    def __str__(self):
        return self.name


class House(models.Model):
    address = models.CharField("Адрес", max_length=255, unique=True)
    section = models.ForeignKey(
        Section, on_delete=models.PROTECT, verbose_name="Участок", related_name="houses"
    )
    is_active = models.BooleanField("Обслуживается", default=True)

    class Meta:
        verbose_name = "Дом"
        verbose_name_plural = "Дома"
        ordering = ["address"]

    def __str__(self):
        return self.address


class Category(models.Model):
    name = models.CharField("Название", max_length=100, unique=True)
    norm_hours = models.PositiveIntegerField("Срок обычной заявки, ч")
    emergency_norm_hours = models.PositiveIntegerField("Срок аварийной заявки, ч")
    is_active = models.BooleanField("Активна", default=True)

    class Meta:
        verbose_name = "Категория"
        verbose_name_plural = "Категории"
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(condition=Q(norm_hours__gt=0), name="category_norm_hours_gt_0"),
            models.CheckConstraint(
                condition=Q(emergency_norm_hours__gt=0), name="category_emergency_hours_gt_0"
            ),
            models.CheckConstraint(
                condition=Q(emergency_norm_hours__lt=models.F("norm_hours")),
                name="category_emergency_lt_norm",
            ),
        ]

    def __str__(self):
        return self.name
