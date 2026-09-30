from django.db import models

class Etapa(models.Model):
    orden = models.PositiveIntegerField(unique=True)
    codigo = models.SlugField(max_length=80, unique=True)
    nombre = models.CharField(max_length=180)
    organismo = models.ForeignKey('organismos.Organismo', on_delete=models.PROTECT, null=True, blank=True, related_name='etapas')
    actor_externo = models.BooleanField(default=False)
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ['orden']
        verbose_name = 'Etapa'
        verbose_name_plural = 'Etapas'

    def __str__(self):
        return f'{self.orden}. {self.nombre}'

class TramiteEtapa(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = 'PENDIENTE', 'Pendiente'
        EN_PROCESO = 'EN_PROCESO', 'En proceso'
        APROBADO = 'APROBADO', 'Aprobado'
        OBSERVADO = 'OBSERVADO', 'Observado'
        RECHAZADO = 'RECHAZADO', 'Rechazado'
        FINALIZADO = 'FINALIZADO', 'Finalizado'

    tramite = models.ForeignKey('tramites.Tramite', on_delete=models.CASCADE, related_name='etapas_historial')
    etapa = models.ForeignKey(Etapa, on_delete=models.PROTECT, related_name='tramites')
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.PENDIENTE)
    fecha_inicio = models.DateTimeField(null=True, blank=True)
    fecha_fin = models.DateTimeField(null=True, blank=True)
    observacion = models.TextField(blank=True)
    usuario = models.ForeignKey('accounts.Usuario', on_delete=models.PROTECT, null=True, blank=True, related_name='actuaciones')

    class Meta:
        ordering = ['etapa__orden']
        unique_together = [('tramite', 'etapa')]
