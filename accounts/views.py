import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.models import Group
from django.contrib.auth.views import PasswordResetView
from django.core import signing
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import LoginForm, RegistrationForm, resolve_house
from .models import ROLE_CHIEF, ROLE_DISPATCHER, ROLE_MASTER, ROLE_RESIDENT, Resident
from .roles import get_role

User = get_user_model()
logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
LOCK_SECONDS = 15 * 60
CONFIRM_SALT = "email-confirm"
CONFIRM_MAX_AGE = 3 * 24 * 3600

ROLE_HOME = {
    ROLE_RESIDENT: "tickets:my",
    ROLE_DISPATCHER: "tickets:queue",
    ROLE_CHIEF: "tickets:queue",
    ROLE_MASTER: "tickets:tasks",
}


def home(request):
    """FR-A5: после входа — главная страница своей роли."""
    if not request.user.is_authenticated:
        return redirect("accounts:login")
    role = get_role(request.user)
    if role in ROLE_HOME:
        return redirect(ROLE_HOME[role])
    if request.user.is_staff:
        return redirect("admin:index")
    return render(request, "accounts/no_role.html", status=403)


def _attempt_key(email):
    return f"login-attempts:{email}"


def _lock_key(email):
    return f"login-lock:{email}"


def login_view(request):
    if request.user.is_authenticated:
        return redirect("home")
    form = LoginForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"].strip().lower()
        if cache.get(_lock_key(email)):
            form.add_error(None, "Слишком много неверных попыток. Повторите вход через 15 минут")
        else:
            user = authenticate(request, username=email, password=form.cleaned_data["password"])
            if user is None:
                attempts = cache.get(_attempt_key(email), 0) + 1
                cache.set(_attempt_key(email), attempts, LOCK_SECONDS)
                if attempts >= MAX_ATTEMPTS:
                    cache.set(_lock_key(email), True, LOCK_SECONDS)
                    cache.delete(_attempt_key(email))
                    logger.warning("Блокировка входа на 15 минут: %s", email)
                if User.objects.filter(username=email, is_active=False).exists():
                    message = "Подтвердите e-mail по ссылке из письма или обратитесь в УК"
                elif attempts >= MAX_ATTEMPTS:
                    message = "Неверный пароль. Вход заблокирован на 15 минут"
                else:
                    left = MAX_ATTEMPTS - attempts
                    message = (
                        f"Неверный e-mail или пароль. Осталось попыток до блокировки на 15 минут: {left}"
                    )
                form.add_error(None, message)
            else:
                cache.delete(_attempt_key(email))
                login(request, user)
                logger.info("Вход в систему: user_id=%s", user.pk)
                return redirect(request.GET.get("next") or "home")
    return render(request, "accounts/login.html", {"form": form})


@require_POST
def logout_view(request):
    logout(request)
    return redirect("accounts:login")


def _send_confirmation(request, user):
    token = signing.dumps(user.pk, salt=CONFIRM_SALT)
    link = request.build_absolute_uri(reverse("accounts:confirm", args=[token]))
    send_mail(
        "Подтверждение e-mail",
        f"Для завершения регистрации перейдите по ссылке:\n{link}\n",
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
    )


def register(request):
    if request.user.is_authenticated:
        return redirect("home")
    form = RegistrationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        with transaction.atomic():
            # До подтверждения e-mail вход закрыт (FR-A3).
            user = User.objects.create_user(
                username=data["email"], email=data["email"], password=data["password1"], is_active=False
            )
            user.groups.add(Group.objects.get(name=ROLE_RESIDENT))
            # Карточка, созданная диспетчером по звонку, связывается с аккаунтом по телефону.
            resident = Resident.objects.filter(user__isnull=True, phone=data["phone"]).first()
            if resident is None:
                resident = Resident(phone=data["phone"])
            resident.user = user
            resident.full_name = data["full_name"]
            resident.email = data["email"]
            resident.house = resolve_house(data)
            resident.apartment = data["apartment"]
            resident.consent_at = timezone.now()
            resident.save()
        try:
            _send_confirmation(request, user)
        except Exception:
            logger.exception("Не удалось отправить письмо подтверждения")
        return render(request, "accounts/register_done.html", {"email": user.email})
    return render(request, "accounts/register.html", {"form": form})


def confirm_email(request, token):
    try:
        user_id = signing.loads(token, salt=CONFIRM_SALT, max_age=CONFIRM_MAX_AGE)
        user = User.objects.get(pk=user_id)
    except (signing.BadSignature, User.DoesNotExist):
        return render(request, "accounts/confirm_failed.html", status=400)
    if not user.is_active:
        user.is_active = True
        user.save(update_fields=["is_active"])
    messages.success(request, "E-mail подтверждён. Теперь можно войти")
    return redirect("accounts:login")


class RuPasswordResetView(PasswordResetView):
    template_name = "accounts/password_reset.html"
    email_template_name = "accounts/password_reset_email.txt"
    subject_template_name = "accounts/password_reset_subject.txt"
    success_url = "/accounts/password-reset/done/"
