from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import ROLE_RESIDENT, Employee, Resident
from directory.models import House, Section

User = get_user_model()

PASSWORD = "Demo-pass-2026"

STAFF = [
    ("dispatcher@uk.local", "Орлова Мария Сергеевна", "+79000000001", "dispatcher", "Участок 1"),
    ("master1@uk.local", "Сидоров Пётр Иванович", "+79000000002", "master", "Участок 1"),
    ("master2@uk.local", "Кузнецов Андрей Павлович", "+79000000003", "master", "Участок 1"),
    ("chief@uk.local", "Новиков Илья Владимирович", "+79000000004", "chief", "Участок 1"),
    ("chief2@uk.local", "Белова Анна Игоревна", "+79000000005", "chief", "Участок 2"),
]


class Command(BaseCommand):
    help = "Создаёт демо-данные: участки, дома, сотрудников и жильца (идемпотентно)"

    @transaction.atomic
    def handle(self, *args, **options):
        sections = {n: Section.objects.get_or_create(name=n)[0] for n in ("Участок 1", "Участок 2")}
        houses = [
            ("г. Калининград, ул. Ленина, 1", "Участок 1"),
            ("г. Калининград, ул. Ленина, 3", "Участок 1"),
            ("г. Калининград, ул. Гагарина, 10", "Участок 2"),
        ]
        house_objs = [
            House.objects.get_or_create(address=a, defaults={"section": sections[s]})[0] for a, s in houses
        ]
        for email, name, phone, role, section in STAFF:
            user, created = User.objects.get_or_create(username=email, defaults={"email": email})
            if created:
                user.set_password(PASSWORD)
                user.save()
            Employee.objects.update_or_create(
                user=user,
                defaults={
                    "full_name": name,
                    "phone": phone,
                    "role": role,
                    "section": sections[section],
                    "is_active": True,
                },
            )
        user, created = User.objects.get_or_create(
            username="resident@uk.local", defaults={"email": "resident@uk.local"}
        )
        if created:
            user.set_password(PASSWORD)
            user.save()
        user.groups.add(Group.objects.get(name=ROLE_RESIDENT))
        Resident.objects.update_or_create(
            user=user,
            defaults={
                "full_name": "Иванов Иван Иванович",
                "phone": "+79001234567",
                "email": "resident@uk.local",
                "house": house_objs[0],
                "apartment": "12",
                "consent_at": timezone.now(),
            },
        )
        self.stdout.write(self.style.SUCCESS(f"Готово. Пароль всех демо-пользователей: {PASSWORD}"))
        self.stdout.write("Логины: resident@, dispatcher@, master1@, master2@, chief@, chief2@ + uk.local")
