from .roles import get_role


def current_role(request):
    user = request.user
    if not user.is_authenticated:
        return {}
    role = get_role(user)
    employee = getattr(user, "employee", None)
    resident = getattr(user, "resident", None)
    person = employee or resident
    return {"role": role, "user_label": person.full_name if person else user.get_username()}
