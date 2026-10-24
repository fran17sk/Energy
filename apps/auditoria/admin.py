from django.contrib import admin
from apps.tramites.admin import SoloLecturaAdmin
from .models import Auditoria


@admin.register(Auditoria)
class AuditoriaAdmin(SoloLecturaAdmin):
    list_display = ('tramite', 'accion', 'usuario', 'creado_en')
    list_filter = ('accion',)
