from django.urls import include, path
from . import views

urlpatterns = [
    path('tramites/<int:pk>/observar/', views.observar_solicitud, name='institucional_observar_solicitud'),
    path('reportes/', include('apps.reportes.urls')),
    path('correos/<int:pk>/reintentar/', views.reintentar_correo, name='institucional_reintentar_correo'),
    path('', views.dashboard, name='institucional_dashboard'),
    path('tramites/', views.lista, name='institucional_tramites'),
    path('tramites/<int:pk>/', views.detalle, name='institucional_tramite_detalle'),
]
