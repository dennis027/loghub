from django.urls import path

from .views import ReportListView, ReportView

urlpatterns = [
    path('reports/', ReportListView.as_view(), name='report-list'),
    path('reports/<slug:key>/', ReportView.as_view(), name='report'),
]
