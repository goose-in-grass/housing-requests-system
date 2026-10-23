import datetime

from django.http import Http404, HttpResponse
from django.shortcuts import render

from accounts.decorators import role_required
from accounts.models import ROLE_CHIEF

from .builders import BUILDERS, REPORTS
from .excel import build_workbook
from .forms import ReportFilterForm, month_start

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@role_required(ROLE_CHIEF)
def index(request):
    return render(request, "reports/index.html", {"reports": REPORTS.items()})


@role_required(ROLE_CHIEF)
def show(request, code):
    if code not in BUILDERS:
        raise Http404
    section = request.user.employee.section
    use_period = code != "overdue"
    data = request.GET.copy()
    if use_period and "date_from" not in data and "date_to" not in data:
        # По умолчанию — текущий месяц.
        data["date_from"] = month_start().isoformat()
        data["date_to"] = datetime.date.today().isoformat()
    form = ReportFilterForm(data, section=section, use_period=use_period)
    result = None
    if form.is_valid():
        result = BUILDERS[code](section, form.cleaned_data)
        if request.GET.get("export") == "xlsx":
            content = build_workbook(REPORTS[code], result["headers"], result["rows"])
            response = HttpResponse(content, content_type=XLSX_TYPE)
            name = f"report_{code}_{datetime.date.today().isoformat()}.xlsx"
            response["Content-Disposition"] = f'attachment; filename="{name}"'
            return response
    return render(
        request,
        "reports/show.html",
        {"code": code, "title": REPORTS[code], "form": form, "result": result, "reports": REPORTS.items()},
    )
