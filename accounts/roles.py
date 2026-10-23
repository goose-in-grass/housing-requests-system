"""Определение роли пользователя и области видимости заявок."""

from .models import ROLE_CHIEF, ROLE_DISPATCHER, ROLE_MASTER, ROLE_RESIDENT


def get_employee(user):
    """Активный сотрудник для пользователя или None."""
    if not user.is_authenticated:
        return None
    employee = getattr(user, "employee", None)
    if employee is not None and employee.is_active and user.is_active:
        return employee
    return None


def get_role(user):
    if not user.is_authenticated or not user.is_active:
        return None
    employee = getattr(user, "employee", None)
    if employee is not None:
        return employee.role if employee.is_active else None
    if getattr(user, "resident", None) is not None:
        return ROLE_RESIDENT
    return None


def is_staff_role(role):
    return role in (ROLE_DISPATCHER, ROLE_MASTER, ROLE_CHIEF)
