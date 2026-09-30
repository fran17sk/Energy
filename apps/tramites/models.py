from django.db import models
from django.utils import timezone

class Tramite(models.Model):
    numero = models.CharField(max_length=30, unique=True, editable=False)
    creado_en = models.DateTimeField(default=timezone.now, editable=False)
    actualizado_en = models.DateTimeField(auto_now=True)

    # Datos del suministro
    nis = models.CharField(max_length=40, db_index=True)
    catastro = models.CharField(max_length=80, blank=True)
    departamento = models.CharField(max_length=100, blank=True)
    potencia_contratada_kw = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)

    # Titular
    titular_nombre = models.CharField(max_length=180)
    titular_dni_cuit = models.CharField(max_length=30)
    titular_email = models.EmailField()
    titular_telefono = models.CharField(max_length=50, blank=True)

    # GGER
    tecnologia = models.CharField(max_length=30, blank=True)
    tipo_conexion = models.CharField(max_length=30, blank=True)
    modalidad_conexion = models.CharField(max_length=120, blank=True)
    potencia_inyectada_kw = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    coordenadas_pilar = models.CharField(max_length=180, blank=True)

    solicitud_factibilidad = models.FileField(upload_to='tramites/%Y/%m/%d/', blank=True, null=True)

    etapa_actual = models.ForeignKey('workflow.Etapa', on_delete=models.PROTECT, null=True, blank=True, related_name='tramites_actuales')
    estado_actual = models.CharField(max_length=20, default='PENDIENTE')
    organismo_actual = models.ForeignKey('organismos.Organismo', on_delete=models.PROTECT, null=True, blank=True, related_name='tramites_actuales')

    class Meta:
        ordering = ['-creado_en']
        indexes = [
            models.Index(fields=['nis']),
            models.Index(fields=['titular_dni_cuit']),
            models.Index(fields=['organismo_actual', 'estado_actual']),
        ]

    def __str__(self):
        return self.numero

    def save(self, *args, **kwargs):
        if not self.numero:
            year = timezone.localdate().year
            last = Tramite.objects.filter(numero__startswith=f'GGER-{year}-').order_by('-id').first()
            next_number = (last.id + 1) if last else 1
            self.numero = f'GGER-{year}-{next_number:06d}'
        super().save(*args, **kwargs)
