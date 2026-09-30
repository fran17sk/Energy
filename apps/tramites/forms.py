from django import forms
from .models import Tramite

class TramitePublicoForm(forms.ModelForm):
    class Meta:
        model = Tramite
        fields = [
            'nis', 'catastro', 'departamento', 'potencia_contratada_kw',
            'titular_nombre', 'titular_dni_cuit', 'titular_email', 'titular_telefono',
            'tecnologia', 'tipo_conexion', 'modalidad_conexion', 'potencia_inyectada_kw',
            'coordenadas_pilar', 'solicitud_factibilidad'
        ]
        widgets = {
            'solicitud_factibilidad': forms.ClearableFileInput(attrs={'accept': '.pdf,.jpg,.jpeg,.png'}),
        }

class ConsultaTramiteForm(forms.Form):
    numero = forms.CharField(max_length=30, label='Número de trámite')
    nis = forms.CharField(max_length=40, label='NIS')
    dni_cuit = forms.CharField(max_length=30, label='DNI / CUIT')
