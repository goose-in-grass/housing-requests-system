from django.db import migrations

# Ориентировочные нормативы из раздела 7 ТЗ (обычная, аварийная), часов.
CATEGORIES = [
    ("Сантехника", 48, 4),
    ("Электрика", 48, 4),
    ("Отопление", 72, 8),
    ("Кровля и фасад", 120, 24),
    ("Лифт", 24, 4),
    ("Двери, окна, места общего пользования", 120, 24),
    ("Уборка и благоустройство", 120, 24),
    ("Прочее", 120, 24),
]


def create_categories(apps, schema_editor):
    Category = apps.get_model("directory", "Category")
    for name, norm, emergency in CATEGORIES:
        Category.objects.get_or_create(
            name=name, defaults={"norm_hours": norm, "emergency_norm_hours": emergency}
        )


class Migration(migrations.Migration):
    dependencies = [("directory", "0001_initial")]

    operations = [migrations.RunPython(create_categories, migrations.RunPython.noop)]
