from django.db import models

class Organismo(models.Model):
    nombre = models.CharField(max_length=150, unique=True)
    sigla = models.CharField(max_length=30, unique=True)
    email_notificaciones = models.EmailField(blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ['nombre']
        verbose_name = 'Organismo'
        verbose_name_plural = 'Organismos'

    def __str__(self):
        return f'{self.sigla} - {self.nombre}'
