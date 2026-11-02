"""
URL configuration for employees app per SRS 4.3.1–4.3.4 and Round 67 specifications.
Routes registered:
- api/v1/positions/ -> PositionListView
- api/v1/employees/summary/ -> EmployeeSummaryView
- api/v1/employees/ -> EmployeeListCreateView
- api/v1/employees/<int:id>/ -> EmployeeDetailView
"""

from django.urls import path

from apps.employees.views.employees import (
    EmployeeDetailView,
    EmployeeListCreateView,
    EmployeeSummaryView,
    PositionListView,
)

app_name = "employees"

urlpatterns = [
    # Danh mục chức vụ phục vụ dropdown (SRS 4.3.1)
    path(
        "positions/",
        PositionListView.as_view(),
        name="position-list",
    ),
    # Thống kê 4 thẻ chỉ số KPI nhân viên (Single Source of Truth)
    path(
        "employees/summary/",
        EmployeeSummaryView.as_view(),
        name="employee-summary",
    ),
    # Danh sách phân trang (GET) & Thêm mới nhân viên (POST)
    path(
        "employees/",
        EmployeeListCreateView.as_view(),
        name="employee-list-create",
    ),
    # Chi tiết (GET), Cập nhật OCC (PATCH) & Xóa mềm DEL-01 (DELETE)
    path(
        "employees/<int:id>/",
        EmployeeDetailView.as_view(),
        name="employee-detail",
    ),
]
