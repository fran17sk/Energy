# Seguimiento GGER

Plataforma web para el registro, seguimiento y trazabilidad de trámites de Generación Distribuida.

## Stack
- Python 3.12+
- Django 5.2.1
- PostgreSQL
- Redis + Celery
- Nginx + Gunicorn
- Django Templates + HTMX (incorporación prevista en la siguiente iteración)

## Alcance de esta primera base
- Portal público: inicio, alta y consulta.
- Usuarios institucionales.
- Organismos.
- Modelo de trámite.
- Workflow parametrizable de 17 etapas.
- Historial de etapas.
- Notificaciones y auditoría como módulos base.
- Dashboard institucional inicial.
- Buscador institucional inicial.

## Instalación local

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env   # Windows
# cp .env.example .env   # Linux
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Luego crear los organismos desde `/admin/` y ejecutar:

```bash
python manage.py seed_workflow
```

## Circuito inicial

El workflow sigue la estructura proporcionada para el proyecto: EDESA, COPAIPA, Secretaría de Minería y ENRESP, con 17 actuaciones hasta la conexión a la red de la Distribuidora.

## Próximas iteraciones
1. Permisos por organismo y por etapa.
2. Motor de transición del workflow.
3. Notificaciones por email + bandeja interna.
4. Historial visual completo.
5. Exportación XLSX/CSV.
6. Dashboard con métricas.
7. Auditoría automática.
8. Protección de consulta pública y rate limiting.
9. Diseño UX/UI definitivo.
10. Pruebas automatizadas y despliegue.
