from django.db import models

class Parametro(models.Model):
    clave = models.CharField(max_length=100, unique=True)
    valor = models.TextField(blank=True)
    descripcion = models.TextField(blank=True)
    activo = models.BooleanField(default=True)

    def __str__(self):
        return self.clave
