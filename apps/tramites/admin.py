from django.contrib import admin
from .models import Tramite, DocumentoTramite, ObservacionSolicitud


class SoloLecturaAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Tramite)
class TramiteAdmin(SoloLecturaAdmin):
    exclude = ('solicitud_factibilidad', 'consulta_documento_hash')
    list_display = ('numero', 'circuito_display', 'nis', 'titular_nombre', 'organismo_actual', 'etapa_actual', 'estado_actual', 'creado_en')
    search_fields = ('numero', 'circuito_display', 'nis', 'titular_nombre', 'titular_dni_cuit')
    list_filter = ('estado_actual', 'organismo_actual')


@admin.register(DocumentoTramite)
class DocumentoAdmin(SoloLecturaAdmin):
    exclude = ('archivo',)
    list_display = ('tramite', 'tipo', 'usuario', 'creado_en')


@admin.register(ObservacionSolicitud)
class ObservacionSolicitudAdmin(SoloLecturaAdmin):
    list_display = ('tramite', 'usuario', 'creada_en', 'subsanada_en', 'recibida_en')
