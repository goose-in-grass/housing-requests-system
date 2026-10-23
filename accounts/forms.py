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
    full_name = forms.CharField(
        label="ФИО",
        max_length=150,
        help_text="От 2 до 150 символов: только буквы, пробелы и дефис. Например: Иванов Иван Иванович",
        error_messages={"required": "Укажите ФИО буквами"},
    )
    phone = forms.CharField(
        label="Телефон",
        max_length=30,
        help_text="11 цифр, начинается с +7 или 8. Например: +7 900 000-00-00",
        error_messages={"required": "Телефон в формате +7 900 000-00-00"},
    )
    email = forms.EmailField(
        label="E-mail",
        help_text="Станет вашим логином. На него придёт ссылка для подтверждения регистрации",
        error_messages={
            "required": "Укажите e-mail",
            "invalid": "Укажите корректный e-mail, например: name@mail.ru",
        },
    )
    house = forms.ModelChoiceField(
        label="Дом",
        queryset=House.objects.none(),
        required=False,
        empty_label="— выберите дом из списка —",
        help_text="Если вашего дома нет в списке, оставьте поле пустым и укажите адрес ниже",
        error_messages={"invalid_choice": "Выберите дом из списка"},
    )
    custom_address = forms.CharField(
        label="Свой адрес (если дома нет в списке)",
        max_length=255,
        required=False,
        help_text=(
            "Город, улица, номер дома. Например: г. Калининград, ул. Мира, 5. "
            "Диспетчер закрепит дом за участком"
        ),
    )
    apartment = forms.CharField(
        label="Квартира",
        max_length=10,
        help_text="До 10 символов: цифры, буквы и «/». Например: 12, 12а, 12/2",
        error_messages={"required": "Укажите номер квартиры"},
    )
    password1 = forms.CharField(
        label="Пароль",
        widget=forms.PasswordInput,
        strip=False,
        help_text=(
            "Не короче 8 символов; не только цифры; не из списка простых паролей "
            "(например, 12345678 или password); не похож на e-mail и не совпадает с ним"
        ),
        error_messages={"required": "Придумайте пароль"},
    )
    password2 = forms.CharField(
        label="Повтор пароля",
        widget=forms.PasswordInput,
        strip=False,
        help_text="Введите тот же пароль ещё раз",
        error_messages={"required": "Повторите пароль"},
    )
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

    def clean_custom_address(self):
        address = " ".join((self.cleaned_data.get("custom_address") or "").split())
        if address and not 5 <= len(address) <= 255:
            raise ValidationError("Укажите адрес полностью: город, улица, дом (от 5 символов)")
        return address

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(username__iexact=email).exists():
            raise ValidationError("Такой e-mail уже зарегистрирован")
        return email

    def clean(self):
        cleaned = super().clean()
        house, address = cleaned.get("house"), cleaned.get("custom_address")
        if not self.errors.get("house") and not self.errors.get("custom_address"):
            if house and address:
                self.add_error(
                    "custom_address", "Выберите дом из списка или укажите свой адрес, но не оба сразу"
                )
            elif not house and not address:
                self.add_error("house", "Выберите дом из списка или укажите свой адрес")
            elif address:
                existing = House.objects.filter(address__iexact=address).first()
                if existing is not None and not existing.is_active:
                    self.add_error("custom_address", "Этот дом не обслуживается управляющей компанией")
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2:
            if p1 != p2:
                self.add_error("password2", "Пароли не совпадают: введите один и тот же пароль дважды")
            elif p1.lower() == (cleaned.get("email") or "").lower():
                self.add_error("password1", "Пароль не должен совпадать с e-mail")
            else:
                try:
                    validate_password(p1, User(username=cleaned.get("email", "")))
                except ValidationError as exc:
                    self.add_error("password1", exc)
        return cleaned


UNASSIGNED_SECTION = "Не распределён"


def resolve_house(cleaned):
    """Дом из списка или новый по введённому адресу.

    Дом по своему адресу создаётся в участке «Не распределён»: диспетчер видит такие
    заявки и закрепляет дом за участком в админке.
    """
    from directory.models import Section

    if cleaned.get("house"):
        return cleaned["house"]
    address = cleaned["custom_address"]
    existing = House.objects.filter(address__iexact=address).first()
    if existing is not None:
        return existing
    section, _ = Section.objects.get_or_create(name=UNASSIGNED_SECTION)
    return House.objects.create(address=address, section=section)


class LoginForm(forms.Form):
    email = forms.EmailField(
        label="E-mail",
        help_text="Тот же адрес, с которым вы регистрировались",
        error_messages={
            "required": "Укажите e-mail",
            "invalid": "Укажите корректный e-mail, например: name@mail.ru",
        },
    )
    password = forms.CharField(
        label="Пароль",
        widget=forms.PasswordInput,
        strip=False,
        help_text="После 5 неверных попыток подряд вход блокируется на 15 минут",
        error_messages={"required": "Введите пароль"},
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_fields(self)
