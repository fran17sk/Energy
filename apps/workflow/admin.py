from django.contrib import admin
from apps.tramites.admin import SoloLecturaAdmin
from .models import Etapa, TramiteEtapa
admin.site.register(Etapa, SoloLecturaAdmin)
admin.site.register(TramiteEtapa, SoloLecturaAdmin)
