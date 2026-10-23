import re

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from directory.models import House

User = get_user_model()

NAME_RE = re.compile(r"^[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё \-]*$")
APARTMENT_RE = re.compile(r"^[0-9A-Za-zА-Яа-яЁё/]{1,10}$")


def style_fields(form):
    """Классы Bootstrap для всех полей формы."""
    for field in form.fields.values():
        widget = field.widget
        if isinstance(widget, forms.CheckboxInput):
            css = "form-check-input"
        elif isinstance(widget, forms.Select):
            css = "form-select"
        else:
            css = "form-control"
        widget.attrs["class"] = f"{widget.attrs.get('class', '')} {css}".strip()


def normalize_phone(value):
    """11 цифр, начинается с +7 или 8; хранится как +7XXXXXXXXXX."""
    digits = re.sub(r"[\s\-()]", "", value or "")
    if re.fullmatch(r"\+7\d{10}", digits):
        return digits
    if re.fullmatch(r"8\d{10}", digits):
        return "+7" + digits[1:]
    raise ValidationError("Телефон в формате +7 900 000-00-00")


def clean_full_name(value):
    value = " ".join((value or "").split())
    if not 2 <= len(value) <= 150 or not NAME_RE.match(value):
        raise ValidationError("Укажите ФИО буквами")
    return value


def clean_apartment(value):
    value = (value or "").strip()
    if not APARTMENT_RE.match(value):
        raise ValidationError("Укажите номер квартиры")
    return value


class RegistrationForm(forms.Form):
    full_name = forms.CharField(label="ФИО", max_length=150)
    phone = forms.CharField(label="Телефон", max_length=30)
    email = forms.EmailField(label="E-mail")
    house = forms.ModelChoiceField(
        label="Дом",
        queryset=House.objects.none(),
        empty_label="— выберите дом —",
        error_messages={"required": "Выберите дом из списка", "invalid_choice": "Выберите дом из списка"},
    )
    apartment = forms.CharField(label="Квартира", max_length=10)
    password1 = forms.CharField(label="Пароль", widget=forms.PasswordInput, strip=False)
    password2 = forms.CharField(label="Повтор пароля", widget=forms.PasswordInput, strip=False)
    consent = forms.BooleanField(
        label="Согласен на обработку персональных данных (152-ФЗ)",
        error_messages={"required": "Без согласия на обработку данных регистрация невозможна"},
    )

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

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(username__iexact=email).exists():
            raise ValidationError("Такой e-mail уже зарегистрирован")
        return email

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2:
            if p1 != p2:
                self.add_error("password2", "Пароли не совпадают")
            elif p1.lower() == (cleaned.get("email") or "").lower():
                self.add_error("password1", "Пароль не должен совпадать с e-mail")
            else:
                try:
                    validate_password(p1, User(username=cleaned.get("email", "")))
                except ValidationError as exc:
                    self.add_error("password1", exc)
        return cleaned


class LoginForm(forms.Form):
    email = forms.EmailField(label="E-mail")
    password = forms.CharField(label="Пароль", widget=forms.PasswordInput, strip=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_fields(self)
