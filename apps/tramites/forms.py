from pathlib import Path
from django import forms
from django.core.exceptions import ValidationError
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
            'solicitud_factibilidad': ('Solicitud de factibilidad', '', 'Adjuntá tu solicitud de factibilidad para EDESA. PDF, JPG o PNG, hasta 10 MB.'),
        }
        self.fields['solicitud_factibilidad'].required = True
        self.fields['solicitud_factibilidad'].validators.append(validar_documento)
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
    numero = forms.CharField(max_length=64, label='Número de trámite')
    nis = forms.CharField(max_length=40, label='NIS')
    dni_cuit = forms.CharField(max_length=30, label='DNI / CUIT')


def validar_documento(archivo):
    if archivo.size > 10 * 1024 * 1024:
        raise ValidationError('El archivo no puede superar los 10 MB.')
    extension = Path(archivo.name).suffix.lower()
    cabecera = archivo.read(8)
    archivo.seek(0)
    valido = (
        (extension == '.pdf' and cabecera.startswith(b'%PDF-')) or
        (extension in {'.jpg', '.jpeg'} and cabecera.startswith(b'\xff\xd8\xff')) or
        (extension == '.png' and cabecera.startswith(b'\x89PNG\r\n\x1a\n'))
    )
    if not valido:
        raise ValidationError('Adjuntá un PDF, JPG o PNG válido.')


class DocumentoForm(forms.Form):
    archivo = forms.FileField(label='Documento', validators=[validar_documento],
        widget=forms.ClearableFileInput(attrs={'accept': '.pdf,.jpg,.jpeg,.png'}))


class AccionTramiteForm(forms.Form):
    accion = forms.ChoiceField(choices=[])
    etapa = forms.CharField(widget=forms.HiddenInput)
    archivo = forms.FileField(required=False, label='Documento', validators=[validar_documento],
        widget=forms.ClearableFileInput(attrs={'accept': '.pdf,.jpg,.jpeg,.png'}))
    expediente = forms.CharField(max_length=100, required=False, label='Número de expediente administrativo')
    fecha = forms.DateTimeField(required=False, label='Fecha y hora',
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local', 'step': '1'}))
    observacion = forms.CharField(max_length=2000, required=False, label='Detalle / indicaciones',
        widget=forms.Textarea(attrs={'rows': 3}))

    def __init__(self, *args, acciones=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['accion'].choices = acciones
        self.fields['accion'].label = 'Actuación'
        codigos = {codigo for codigo, _ in acciones}
        if len(acciones) == 1:
            self.fields['accion'].widget = forms.HiddenInput()
            self.fields['accion'].initial = acciones[0][0]
        if not codigos.intersection({'respuesta', 'copaipa', 'dictamen', 'resolucion', 'contrato'}):
            self.fields.pop('archivo')
        if 'expediente' not in codigos:
            self.fields.pop('expediente')
        if not codigos.intersection({'programar', 'inspeccionar', 'conectar'}):
            self.fields.pop('fecha')

        required_messages = {
            'archivo': 'Esta actuación requiere un documento.',
            'expediente': 'Ingresá el número de expediente.',
            'fecha': 'Ingresá la fecha y hora de la actuación.',
        }
        for name, message in required_messages.items():
            if name in self.fields:
                self.fields[name].required = True
                self.fields[name].error_messages['required'] = message
        if 'convocar' in codigos:
            self.fields['observacion'].required = True
            self.fields['observacion'].error_messages['required'] = 'Indicá la oficina y las instrucciones para firmar el contrato.'
        if codigos == {'recibir'}:
            self.fields.pop('observacion')
