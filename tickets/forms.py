from django import forms
from django.db.models import Q

from accounts.forms import clean_apartment, clean_full_name, normalize_phone, style_fields
from accounts.models import ROLE_MASTER, Employee, Resident
from directory.models import Category, House

from .models import Priority, Status


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        if not data:
            return []
        files = data if isinstance(data, (list, tuple)) else [data]
        return [super(MultipleFileField, self).clean(f, initial) for f in files]


PHOTO_WIDGET_ATTRS = {"accept": "image/jpeg,image/png,image/webp", "multiple": True}


class TicketCreateForm(forms.Form):
    category = forms.ModelChoiceField(
        label="Категория",
        queryset=Category.objects.none(),
        empty_label="— выберите категорию —",
        error_messages={"required": "Выберите категорию", "invalid_choice": "Выберите категорию"},
    )
    description = forms.CharField(
        label="Описание проблемы",
        widget=forms.Textarea(attrs={"rows": 5}),
        max_length=2000,
        error_messages={"required": "Опишите проблему (от 10 символов)"},
    )
    photos = MultipleFileField(
        label="Фото (до 5 шт., JPG, PNG или WebP до 5 МБ)",
        required=False,
        widget=MultipleFileInput(attrs={**PHOTO_WIDGET_ATTRS, "capture": "environment"}),
    )
    emergency = forms.BooleanField(label="Это авария", required=False)
    priority = forms.ChoiceField(
        label="Приоритет", choices=Priority.choices, required=False, initial=Priority.NORMAL
    )

    def __init__(self, *args, is_dispatcher=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_dispatcher = is_dispatcher
        self.fields["category"].queryset = Category.objects.filter(is_active=True)
        if is_dispatcher:
            del self.fields["emergency"]
        else:
            del self.fields["priority"]
        style_fields(self)

    def clean_description(self):
        text = self.cleaned_data["description"].strip()
        if len(text) < 10:
            raise forms.ValidationError("Опишите проблему (от 10 символов)")
        return text

    def clean_photos(self):
        from django.core.exceptions import ValidationError

        from .validators import validate_photos

        try:
            return validate_photos(self.cleaned_data.get("photos") or [])
        except ValidationError as exc:
            raise forms.ValidationError(exc.messages[0]) from exc


class ResidentSearchForm(forms.Form):
    q = forms.CharField(label="Поиск жильца (ФИО, телефон, адрес)", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_fields(self)

    def search(self):
        q = (self.cleaned_data.get("q") or "").strip()
        if not q:
            return Resident.objects.none()
        return Resident.objects.select_related("house").filter(
            Q(full_name__icontains=q) | Q(phone__icontains=q) | Q(house__address__icontains=q)
        )[:20]


class NewResidentForm(forms.Form):
    """Краткая карточка жильца без личного кабинета (FR-D2)."""

    full_name = forms.CharField(label="ФИО", max_length=150)
    phone = forms.CharField(label="Телефон", max_length=30)
    house = forms.ModelChoiceField(
        label="Дом",
        queryset=House.objects.none(),
        error_messages={"required": "Выберите дом из списка", "invalid_choice": "Выберите дом из списка"},
    )
    apartment = forms.CharField(label="Квартира", max_length=10)
    email = forms.EmailField(label="E-mail (необязательно)", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["house"].queryset = House.objects.filter(is_active=True)
        style_fields(self)

    def clean_full_name(self):
        return clean_full_name(self.cleaned_data["full_name"])

    def clean_phone(self):
        return normalize_phone(self.cleaned_data["phone"])

    def clean_apartment(self):
        return clean_apartment(self.cleaned_data["apartment"])


class QueueFilterForm(forms.Form):
    STATUS_CHOICES = [("", "Все статусы"), ("active", "Все активные"), ("overdue", "Просроченные")] + list(
        Status.choices
    )

    status = forms.ChoiceField(label="Статус", choices=STATUS_CHOICES, required=False)
    house = forms.ModelChoiceField(
        label="Дом", queryset=House.objects.none(), required=False, empty_label="Все дома"
    )
    category = forms.ModelChoiceField(
        label="Категория", queryset=Category.objects.all(), required=False, empty_label="Все категории"
    )
    priority = forms.ChoiceField(
        label="Приоритет", choices=[("", "Любой")] + list(Priority.choices), required=False
    )
    master = forms.ModelChoiceField(
        label="Мастер", queryset=Employee.objects.none(), required=False, empty_label="Все мастера"
    )
    q = forms.CharField(label="Номер или адрес", required=False)

    def __init__(self, *args, section=None, **kwargs):
        super().__init__(*args, **kwargs)
        houses = House.objects.all()
        masters = Employee.objects.filter(role=ROLE_MASTER)
        if section is not None:
            houses = houses.filter(section=section)
            masters = masters.filter(section=section)
        self.fields["house"].queryset = houses
        self.fields["master"].queryset = masters
        style_fields(self)


class MyTicketsFilterForm(forms.Form):
    status = forms.ChoiceField(
        label="Статус", choices=[("", "Все статусы")] + list(Status.choices), required=False
    )
    q = forms.CharField(label="Номер заявки", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_fields(self)
