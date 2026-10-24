from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='institucional_reportes'),
    path('exportar/', views.exportar, name='institucional_reportes_exportar'),
]
