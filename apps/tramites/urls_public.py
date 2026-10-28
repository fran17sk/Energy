from django.urls import path
from . import views

urlpatterns = [
    path('tramites/solicitud-enviada/', views.solicitud_enviada, name='solicitud_enviada'),
    path('tramites/documentos/<int:pk>/', views.documento, name='tramite_documento'),
    path('tramites/<int:pk>/proyecto/', views.proyecto_cliente, name='tramite_proyecto'),
    path('', views.inicio, name='inicio'),
    path('tramites/nuevo/', views.nuevo, name='tramite_nuevo'),
    path('tramites/consultar/', views.consultar, name='tramite_consultar'),
]
