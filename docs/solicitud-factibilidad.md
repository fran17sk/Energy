# Solicitud de factibilidad y registro mínimo

## Formulario

La presentación pública tiene seis secciones:

1. Propietario del inmueble: tipo de persona, nombre/razón social y DNI para persona humana o CUIT para jurídica.
2. Titular del suministro: los mismos datos, independientes de los del propietario.
3. Suministro: NIS, potencia contratada con EDESA (kW), catastro y uno de los 23 departamentos de Salta.
4. Equipamiento: sistema fotovoltaico, eólico, biomasa o hidráulico; conexión monofásica 220 V, trifásica 380 V, media tensión 13,2 kV o 33 kV; potencia efectiva a plena carga inyectada en corriente alterna; coordenadas del pilar de medición.
5. Solicitante: titular o apoderado, nombre, DNI, celular y correo para notificaciones. Este correo es el destino de las comunicaciones posteriores, aunque sea distinto del titular.
6. Adjuntos: formulario digital y DNI del titular (o de su representante, si es persona jurídica); al intervenir un apoderado se exigen además su DNI y el poder correspondiente.

El formulario valida los campos condicionales tanto en el navegador como en el servidor. El DNI admite 7 u 8 dígitos y el CUIT 11, normalizando separadores; esto es validación de formato, no acreditación de identidad. Las coordenadas deben tener formato `latitud, longitud`, con punto decimal y valores válidos. Las potencias son positivas.

Se aceptan PDF, JPG y PNG con firma inicial acorde a su extensión. El límite es de 5 MB por archivo y 15 MB entre todos los adjuntos. No hay borradores ni guardado de los campos en localStorage.

## Dirección receptora configurable

En el `.env` de la instalación, junto a `manage.py`:

```dotenv
EDESA_SOLICITUD_EMAIL=correo-designado-por-edesa@example.com
```

Reemplazar el ejemplo por la dirección autorizada. La dirección se valida y no se infiere de `EMAIL_HOST_USER`. También deben estar configuradas las variables SMTP de `.env.example`. Reiniciar los procesos después de cambiar el entorno.

Para Gmail, el transporte habitual usa puerto 587 y `EMAIL_USE_TLS=True`; la contraseña de aplicación se configura de forma privada en `EMAIL_HOST_PASSWORD`, fuera de Git. El envío se hace desde `DEFAULT_FROM_EMAIL`, al destino de EDESA, con `Reply-To` al solicitante. El correo lleva la presentación completa en texto y HTML, el código de referencia y todos los adjuntos aplicables con nombres seguros.

Si el destino no está configurado, SMTP falla o el backend no acepta el mensaje, no se muestra una confirmación de envío ni se conserva un registro incompleto. Los backends de consola y archivo están bloqueados para esta presentación porque volcarían su contenido a logs o disco. El backend en memoria se admite para pruebas y no entrega correos reales.

## Qué se guarda y qué no

Se conserva el mínimo autorizado para continuar el circuito:

- Código aleatorio del trámite y NIS.
- Correo del solicitante para notificaciones.
- Hash con sal del DNI o CUIT del titular para comprobar las consultas, sin guardar ese documento en texto plano.
- Identificador técnico de la modalidad de presentación, etapa, organismo, estado, fechas e historial operativo/auditoría.
- Notificación del código al solicitante, con contenido genérico de seguimiento y su estado de envío.

No se guardan los nombres del propietario, titular o solicitante; DNI/CUIT en texto plano; celular; catastro; departamento; potencias; tecnología; conexión; coordenadas; ni los adjuntos iniciales. Esos datos y documentos se envían únicamente por correo a EDESA. El registro mínimo no tiene archivo de solicitud ni filas iniciales en `DocumentoTramite`. En las vistas se identifica como `Suministro NIS …`, sin inventar un nombre de titular.

El formulario es un `forms.Form` independiente del modelo, y el registro usa una lista explícita de campos permitidos. El receptor procesa los archivos exclusivamente en RAM mediante un upload handler instalado antes de la comprobación CSRF; una vista interna vuelve a exigir CSRF. Se impiden archivos temporales incluso cuando los handlers generales de Django usarían disco. No se registra el contenido de la presentación en logs ni se utiliza una cola persistente para el correo completo.

La aceptación SMTP y la creación mínima se coordinan en una transacción. No se conserva el contenido completo para reintentos: si el envío falla, el solicitante debe volver a adjuntar los documentos. Como SMTP y la base no comparten una transacción distribuida, un corte después de la aceptación SMTP puede dejar un correo recibido sin una confirmación completa del registro; ante un fallo en ese punto conviene verificar con EDESA antes de reenviar.

El código al solicitante se envía por la bandeja de notificaciones del circuito, después de confirmar la transacción. Si ese segundo correo falla, el registro mínimo sigue válido, el código se muestra en pantalla y el correo del código puede reintentarse. La confirmación usa una cookie firmada, HttpOnly y de diez minutos, que contiene sólo el identificador técnico; no guarda el formulario en sesión ni incluye datos o códigos en la URL. Recargar esa pantalla no reenvía la presentación.

## Continuidad del circuito

El registro mínimo se asigna al ingreso de EDESA. La consulta sigue usando código + NIS + DNI/CUIT del titular, comparando el documento con su hash. Después continúan las recepciones, respuesta de factibilidad, Proyecto Ejecutivo, dictámenes, contrato, inspección y conexión existentes. Los documentos agregados en esas etapas posteriores siguen el almacenamiento privado del circuito; la exclusión de almacenamiento corresponde a la presentación y adjuntos iniciales.

Los trámites anteriores mantienen sus datos y archivos y conservan la consulta habitual. Las métricas de tiempos y cantidades incluyen los nuevos registros mínimos. No se pueden reconstruir métricas geográficas o técnicas sobre campos que no se guardan.

## Despliegue y comprobaciones

```bash
python manage.py migrate --noinput
python manage.py check
python manage.py test --noinput
```

Configurar `EDESA_SOLICITUD_EMAIL`, las credenciales SMTP y reiniciar Django. En producción, publicar por HTTPS. El proxy y las herramientas de monitoreo tampoco deben registrar cuerpos de formulario ni adjuntos. Si se usa Nginx, desactivar el buffering del cuerpo hacia la aplicación (`proxy_request_buffering off` con HTTP/1.1) y evitar que los cuerpos se vuelquen a temporales; alinear el límite total del proxy con los 16 MB máximos de petición multipart que admite la aplicación. La aplicación por sí sola no controla archivos o logs generados por infraestructura externa.

La suite comprueba campos y adjuntos condicionales, tipos de persona, opciones permitidas, límites, CSRF, ausencia de archivos temporales y guardado de adjuntos, ausencia de datos completos en SQL, rollback ante fallo SMTP, consulta protegida, continuidad del circuito y no duplicación al recargar la confirmación.
