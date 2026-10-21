from django import forms
from .models import Tramite

class TramitePublicoForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        details = {
            'nis': ('NIS del suministro', 'Ej.: 1234567', 'Encontralo en tu factura de energía.'),
            'catastro': ('Catastro', 'Número de catastro', ''),
            'departamento': ('Departamento', 'Ej.: Capital', ''),
            'potencia_contratada_kw': ('Potencia contratada (kW)', 'Ej.: 5', ''),
            'titular_nombre': ('Nombre y apellido / Razón social', 'Tal como figura en la documentación', ''),
            'titular_dni_cuit': ('DNI / CUIT', 'Documento del titular', 'Conservá este dato: lo vas a necesitar para consultar el trámite.'),
            'titular_email': ('Correo electrónico', 'nombre@ejemplo.com', ''),
            'titular_telefono': ('Teléfono de contacto', 'Ej.: +54 387 123 4567', ''),
            'tecnologia': ('Tecnología de generación', 'Ej.: Solar fotovoltaica', ''),
            'tipo_conexion': ('Tipo de conexión', 'Ej.: Monofásica', ''),
            'modalidad_conexion': ('Modalidad de conexión', 'Indicá la modalidad del proyecto', ''),
            'potencia_inyectada_kw': ('Potencia a inyectar (kW)', 'Ej.: 3', ''),
            'coordenadas_pilar': ('Coordenadas del pilar', 'Ej.: -24.7821, -65.4232', 'Ingresá latitud y longitud, si las tenés disponibles.'),
            'solicitud_factibilidad': ('Solicitud de factibilidad', '', 'Adjuntá la solicitud presentada ante EDESA. Podés seleccionar un archivo PDF, JPG o PNG.'),
        }
        autocomplete = {'titular_nombre': 'name', 'titular_email': 'email', 'titular_telefono': 'tel'}
        for name, (label, placeholder, help_text) in details.items():
            field = self.fields[name]
            field.label = label
            field.help_text = help_text
            field.widget.attrs.update({'class': 'alta-input', 'aria-describedby': f'id_{name}_help id_{name}_errors'})
            if placeholder:
                field.widget.attrs['placeholder'] = placeholder
            if name in autocomplete:
                field.widget.attrs['autocomplete'] = autocomplete[name]
            if self.is_bound and name in self.errors:
                field.widget.attrs['aria-invalid'] = 'true'

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
