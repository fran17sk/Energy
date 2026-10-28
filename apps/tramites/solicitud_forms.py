"""Formulario de solicitud independiente de los modelos de seguimiento."""
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from django import forms
from django.core.exceptions import ValidationError

DEPARTAMENTOS_SALTA = [
    'Anta', 'Cachi', 'Cafayate', 'Capital', 'Cerrillos', 'Chicoana', 'General Güemes',
    'General José de San Martín', 'Guachipas', 'Iruya', 'La Caldera', 'La Candelaria',
    'La Poma', 'La Viña', 'Los Andes', 'Metán', 'Molinos', 'Orán', 'Rivadavia',
    'Rosario de la Frontera', 'Rosario de Lerma', 'San Carlos', 'Santa Victoria',
]
PERSONAS = [('HUMANA', 'Persona humana'), ('JURIDICA', 'Persona jurídica')]
TECNOLOGIAS = [('FOTOVOLTAICO', 'Sistema fotovoltaico'), ('EOLICO', 'Sistema eólico'),
               ('BIOMASA', 'Sistema biomasa'), ('HIDRAULICO', 'Sistema hidráulico')]
CONEXIONES = [('MONOFASICA_220', 'Monofásica (220 V)'), ('TRIFASICA_380', 'Trifásica (380 V)'),
              ('MEDIA_13_2', 'Media tensión (13,2 kV)'), ('MEDIA_33', 'Media tensión (33 kV)')]
MAX_ARCHIVO = 5 * 1024 * 1024
MAX_ADJUNTOS = 15 * 1024 * 1024


def validar_adjunto(archivo):
    if archivo.size > MAX_ARCHIVO:
        raise ValidationError('Cada archivo puede pesar hasta 5 MB.')
    cabecera = archivo.read(8)
    archivo.seek(0)
    extension = Path(archivo.name).suffix.lower()
    valido = ((extension == '.pdf' and cabecera.startswith(b'%PDF-')) or
              (extension in {'.jpg', '.jpeg'} and cabecera.startswith(b'\xff\xd8\xff')) or
              (extension == '.png' and cabecera.startswith(b'\x89PNG\r\n\x1a\n')))
    if not valido:
        raise ValidationError('Adjuntá un archivo PDF, JPG o PNG válido.')


def adjunto(label, required=True):
    return forms.FileField(label=label, required=required, validators=[validar_adjunto],
        widget=forms.ClearableFileInput(attrs={'accept': '.pdf,.jpg,.jpeg,.png'}))


class SolicitudFactibilidadForm(forms.Form):
    requiere_adjuntos_apoderado = True
    propietario_tipo = forms.ChoiceField(label='Tipo de persona', choices=PERSONAS, initial='HUMANA')
    propietario_nombre = forms.CharField(label='Nombre completo / Razón social', max_length=180)
    propietario_dni = forms.CharField(label='DNI del propietario', max_length=15, required=False)
    propietario_cuit = forms.CharField(label='CUIT del propietario', max_length=15, required=False)
    titular_tipo = forms.ChoiceField(label='Tipo de persona', choices=PERSONAS, initial='HUMANA')
    titular_nombre = forms.CharField(label='Nombre completo / Razón social', max_length=180)
    titular_dni = forms.CharField(label='DNI del titular', max_length=15, required=False)
    titular_cuit = forms.CharField(label='CUIT del titular', max_length=15, required=False)
    nis = forms.RegexField(label='NIS', regex=r'^[0-9]{1,40}$', max_length=40,
        error_messages={'invalid': 'Ingresá el NIS con números, tal como figura en la factura.'})
    potencia_contratada_kw = forms.DecimalField(label='Potencia contratada con EDESA (kW)', max_digits=12,
        decimal_places=3, min_value=Decimal('0.001'))
    catastro = forms.CharField(label='Catastro N.º', max_length=80)
    departamento = forms.ChoiceField(label='Departamento de Salta', choices=[('', 'Seleccioná un departamento')] + [(d, d) for d in DEPARTAMENTOS_SALTA])
    tecnologia = forms.ChoiceField(label='Tecnología del GGER', choices=[('', 'Seleccioná una tecnología')] + TECNOLOGIAS)
    tipo_conexion = forms.ChoiceField(label='Tipo de conexión', choices=[('', 'Seleccioná el tipo de conexión')] + CONEXIONES)
    potencia_inyectada_kw = forms.DecimalField(label='Potencia efectiva a plena carga inyectada en corriente alterna (kW)',
        max_digits=12, decimal_places=3, min_value=Decimal('0.001'))
    coordenadas_pilar = forms.CharField(label='Ubicación del pilar de medición del GGER', max_length=80,
        help_text='Pegá las coordenadas de Google Maps: latitud, longitud. Ejemplo: -24.7821, -65.4232.')
    solicitante_condicion = forms.ChoiceField(label='El solicitante actúa como',
        choices=[('TITULAR', 'Titular del suministro'), ('APODERADO', 'Apoderado')], initial='TITULAR')
    solicitante_nombre = forms.CharField(label='Nombre completo del solicitante', max_length=180)
    solicitante_dni = forms.CharField(label='DNI del solicitante', max_length=15)
    solicitante_celular = forms.CharField(label='Celular', max_length=30)
    solicitante_email = forms.EmailField(label='Dirección electrónica para notificaciones', max_length=254,
        help_text='EDESA utilizará este correo para las comunicaciones sobre tu solicitud.')
    formulario_digital = adjunto('Formulario digital')
    dni_titular = adjunto('Fotocopia del DNI del titular')
    dni_apoderado = adjunto('Fotocopia del DNI del apoderado', required=False)
    poder_apoderado = adjunto('Poder otorgado al apoderado / abogado', required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs.update({'class': 'alta-input', 'aria-describedby': f'id_{name}_help id_{name}_errors'})
        for name in ['propietario_dni', 'titular_dni', 'solicitante_dni', 'propietario_cuit', 'titular_cuit', 'nis']:
            self.fields[name].widget.attrs['inputmode'] = 'numeric'
        self.fields['solicitante_celular'].widget = forms.TextInput(attrs={
            **self.fields['solicitante_celular'].widget.attrs, 'type': 'tel', 'autocomplete': 'tel'})
        self.fields['solicitante_email'].widget.attrs['autocomplete'] = 'email'
        self.fields['solicitante_nombre'].widget.attrs['autocomplete'] = 'name'
        self.fields['coordenadas_pilar'].widget.attrs['placeholder'] = '-24.7821, -65.4232'

    def _documento(self, value, tipo):
        value = re.sub(r'[.\s-]', '', value or '')
        patron = r'[0-9]{7,8}' if tipo == 'DNI' else r'[0-9]{11}'
        if not re.fullmatch(patron, value):
            raise ValidationError('Ingresá un DNI de 7 u 8 dígitos.' if tipo == 'DNI' else 'Ingresá un CUIT de 11 dígitos.')
        return value

    def clean_solicitante_dni(self):
        return self._documento(self.cleaned_data['solicitante_dni'], 'DNI')

    def clean_solicitante_celular(self):
        value = self.cleaned_data['solicitante_celular']
        digitos = re.sub(r'\D', '', value)
        if not re.fullmatch(r'\+?[0-9()\s-]+', value) or not 8 <= len(digitos) <= 15:
            raise ValidationError('Ingresá un celular válido, con código de área.')
        return value

    def clean_coordenadas_pilar(self):
        value = self.cleaned_data['coordenadas_pilar']
        try:
            latitud, longitud = [Decimal(p.strip()) for p in value.split(',')]
            if not latitud.is_finite() or not longitud.is_finite() or not (-90 <= latitud <= 90 and -180 <= longitud <= 180):
                raise ValueError
        except (ValueError, InvalidOperation):
            raise ValidationError('Ingresá latitud y longitud válidas, separadas por una coma y con punto decimal.')
        return f'{latitud}, {longitud}'

    def clean(self):
        data = super().clean()
        for persona in ['propietario', 'titular']:
            tipo = data.get(f'{persona}_tipo')
            if tipo not in {'HUMANA', 'JURIDICA'}:
                continue
            activo, inactivo, documento = ('dni', 'cuit', 'DNI') if tipo == 'HUMANA' else ('cuit', 'dni', 'CUIT')
            field = f'{persona}_{activo}'
            try:
                data[field] = self._documento(data.get(field), documento)
            except ValidationError as exc:
                self.add_error(field, exc)
            data[f'{persona}_{inactivo}'] = ''
        if data.get('solicitante_condicion') == 'APODERADO':
            for field in ['dni_apoderado', 'poder_apoderado']:
                if self.requiere_adjuntos_apoderado and not data.get(field):
                    self.add_error(field, 'Este documento es obligatorio cuando interviene un apoderado.')
        else:
            data['dni_apoderado'] = data['poder_apoderado'] = None
        archivos = [data.get(n) for n in ['formulario_digital', 'dni_titular', 'dni_apoderado', 'poder_apoderado']]
        if sum(a.size for a in archivos if a) > MAX_ADJUNTOS:
            raise ValidationError('Los adjuntos pueden sumar hasta 15 MB en total.')
        return data
