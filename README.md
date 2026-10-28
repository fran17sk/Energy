# Seguimiento GGER

Plataforma web para el registro, seguimiento y trazabilidad de trámites de Generación Distribuida.

## Stack
- Python 3.12+
- Django 5.2.1
- PostgreSQL
- Redis + Celery
- Nginx + Gunicorn
- Django Templates + HTMX (incorporación prevista en la siguiente iteración)

## Circuito operativo

Solicitud de factibilidad → EDESA → Proyecto Ejecutivo del cliente → Previsado EDESA → Visado COPAIPA → Expediente y dictamen de la Secretaría de Minería y Energía → Resolución ENRESP → Contrato EDESA → Inspección → Conexión y cierre.

Cada organismo ve el estado completo y sólo actúa cuando la etapa le corresponde. Toda recepción y actuación registra usuario, organismo, fecha y hora. Los clientes consultan y adjuntan el proyecto usando el código seguro, NIS y DNI/CUIT.

Ver [operación, permisos, correo y actualización](docs/circuito.md).

## Instalación local

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env   # Windows
# cp .env.example .env   # Linux
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Luego crear los organismos desde `/admin/` y ejecutar:

```bash
python manage.py seed_workflow
```

## Configuración de correo y documentos

Configurar SMTP con las variables de `.env.example` para enviar los códigos y notificaciones. Los errores quedan registrados para reintentar con `python manage.py reenviar_notificaciones`.

Los documentos se guardan en almacenamiento privado y se descargan con autorización. No exponer `media/` ni `private_uploads/` como rutas estáticas. Consultar [las instrucciones de despliegue](docs/circuito.md#actualización) antes de actualizar una instalación existente.

## Reportes institucionales

El menú **Reportes y estadísticas** permite analizar cantidades, tiempos de recepción y respuesta por organismo, evolución de altas y gestiones pendientes. Incluye filtros de fechas/organismo y exportación CSV. Ver [definiciones y alcance de los indicadores](docs/reportes.md).

## Nueva solicitud de factibilidad

El formulario se divide en propietario, titular del suministro, suministro, equipamiento GGER, solicitante y documentación. El envío completo y los adjuntos iniciales se remiten al correo configurado en `EDESA_SOLICITUD_EMAIL`. Se guardan todos los datos del formulario para gestionar el expediente. Los adjuntos iniciales se envían sólo por correo y no se almacenan en el servidor. Ver [configuración y política de almacenamiento](docs/solicitud-factibilidad.md).
