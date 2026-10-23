from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models

PHONE_VALIDATOR = RegexValidator(r"^\+7\d{10}$", "Телефон в формате +7 900 000-00-00")

ROLE_RESIDENT = "resident"
ROLE_DISPATCHER = "dispatcher"
ROLE_MASTER = "master"
ROLE_CHIEF = "chief"
ROLE_GROUPS = (ROLE_RESIDENT, ROLE_DISPATCHER, ROLE_MASTER, ROLE_CHIEF)


class Resident(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="resident"
    )
    full_name = models.CharField("ФИО", max_length=150)
    phone = models.CharField("Телефон", max_length=12, validators=[PHONE_VALIDATOR])
    email = models.EmailField("E-mail", blank=True)
    house = models.ForeignKey(
        "directory.House", on_delete=models.PROTECT, verbose_name="Дом", related_name="residents"
    )
    apartment = models.CharField("Квартира", max_length=10)
    consent_at = models.DateTimeField("Согласие на обработку данных", null=True, blank=True)

    class Meta:
        verbose_name = "Жилец"
        verbose_name_plural = "Жильцы"
        ordering = ["full_name"]

    def __str__(self):
        return f"{self.full_name}, {self.house}, кв. {self.apartment}"


class Employee(models.Model):
    ROLE_CHOICES = [
        (ROLE_DISPATCHER, "Диспетчер"),
        (ROLE_MASTER, "Мастер"),
        (ROLE_CHIEF, "Начальник участка"),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="employee")
    full_name = models.CharField("ФИО", max_length=150)
    phone = models.CharField("Телефон", max_length=12, validators=[PHONE_VALIDATOR])
    role = models.CharField("Роль", max_length=20, choices=ROLE_CHOICES)
    section = models.ForeignKey(
        "directory.Section", on_delete=models.PROTECT, verbose_name="Участок", related_name="employees"
    )
    is_active = models.BooleanField("Активен", default=True)

    class Meta:
        verbose_name = "Сотрудник"
        verbose_name_plural = "Сотрудники"
        ordering = ["full_name"]

    def __str__(self):
        return f"{self.full_name} ({self.get_role_display()})"
