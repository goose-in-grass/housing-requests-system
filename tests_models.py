import pytest
from django.contrib.auth.models import Group, User
from django.db import IntegrityError, transaction

from directory.models import Category, House, Section
from tickets.models import StatusHistory, Ticket


@pytest.fixture
def ticket(db):
    section = Section.objects.create(name="Участок 1")
    house = House.objects.create(address="ул. Ленина, 1", section=section)
    from accounts.models import Resident

    user = User.objects.create_user("a@b.ru", "a@b.ru", "pass12345")
    resident = Resident.objects.create(
        full_name="Иванов Иван", phone="+79000000000", house=house, apartment="1"
    )
    return Ticket.objects.create(
        number="2026-000001",
        resident=resident,
        created_by=user,
        category=Category.objects.get(name="Сантехника"),
        house=house,
        apartment="1",
        description="Течёт кран на кухне",
    )


def test_role_groups_created_by_migration(db):
    names = set(Group.objects.values_list("name", flat=True))
    assert {"resident", "dispatcher", "master", "chief"} <= names


def test_default_categories_match_spec(db):
    assert Category.objects.count() == 8
    plumbing = Category.objects.get(name="Сантехника")
    assert (plumbing.norm_hours, plumbing.emergency_norm_hours) == (48, 4)


def test_emergency_norm_must_be_less_than_normal(db):
    with pytest.raises(IntegrityError), transaction.atomic():
        Category.objects.create(name="Плохая", norm_hours=4, emergency_norm_hours=4)


def test_ticket_defaults(ticket):
    assert ticket.status == "new"
    assert ticket.priority == "normal"
    assert ticket.version == 1


def test_history_is_immutable(ticket):
    entry = StatusHistory.objects.create(
        ticket=ticket, event="status", new_status="new", changed_by=ticket.created_by
    )
    entry.comment = "правка"
    with pytest.raises(ValueError):
        entry.save()
    with pytest.raises(ValueError):
        entry.delete()
