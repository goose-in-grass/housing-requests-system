import datetime

from django import forms

from accounts.forms import style_fields
from accounts.models import ROLE_MASTER, Employee
from directory.models import Category, House


def month_start():
    return datetime.date.today().replace(day=1)


class ReportFilterForm(forms.Form):
    date_from = forms.DateField(label="С", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    date_to = forms.DateField(label="По", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    house = forms.ModelChoiceField(
        label="Дом", queryset=House.objects.none(), required=False, empty_label="Все дома"
    )
    category = forms.ModelChoiceField(
        label="Категория", queryset=Category.objects.all(), required=False, empty_label="Все категории"
    )
    master = forms.ModelChoiceField(
        label="Мастер", queryset=Employee.objects.none(), required=False, empty_label="Все мастера"
    )

    def __init__(self, *args, section, use_period=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["house"].queryset = House.objects.filter(section=section)
        self.fields["master"].queryset = Employee.objects.filter(role=ROLE_MASTER, section=section)
        if not use_period:
            del self.fields["date_from"], self.fields["date_to"]
        style_fields(self)

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("date_from"), cleaned.get("date_to")
        if start and end and start > end:
            raise forms.ValidationError("Начало периода позже конца")
        return cleaned
