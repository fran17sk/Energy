from django.contrib import admin
from apps.tramites.admin import SoloLecturaAdmin
from .models import Notificacion
admin.site.register(Notificacion, SoloLecturaAdmin)
