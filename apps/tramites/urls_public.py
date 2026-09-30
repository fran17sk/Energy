from django.urls import path
from . import views

urlpatterns = [
    path('', views.inicio, name='inicio'),
    path('tramites/nuevo/', views.nuevo, name='tramite_nuevo'),
    path('tramites/consultar/', views.consultar, name='tramite_consultar'),
]
