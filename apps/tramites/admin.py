from django.contrib import admin
from .models import Tramite
@admin.register(Tramite)
class TramiteAdmin(admin.ModelAdmin):
    list_display = ('numero','nis','titular_nombre','organismo_actual','etapa_actual','estado_actual','creado_en')
    search_fields = ('numero','nis','titular_nombre','titular_dni_cuit')
    list_filter = ('estado_actual','organismo_actual')
