from django.db import models

class Auditoria(models.Model):
    creado_en = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey('accounts.Usuario', on_delete=models.PROTECT, null=True, blank=True)
    tramite = models.ForeignKey('tramites.Tramite', on_delete=models.CASCADE, related_name='auditorias')
    accion = models.CharField(max_length=80)
    detalle = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-creado_en']
