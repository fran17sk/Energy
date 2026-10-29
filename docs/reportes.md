# Reportes y estadísticas

Acceso institucional: `/institucional/reportes/`. Disponible para cuentas activas con organismo, incluido el rol de consulta, y superusuarios. El módulo sólo consulta información; no confirma recepciones ni modifica etapas. La navegación lateral incluye el acceso directo.

## Selección del período

Se seleccionan trámites por **fecha de inicio** en hora local de Salta, incluyendo ambos días. Por defecto se muestran los últimos 90 días. El rango máximo admitido es de 3660 días. El filtro por organismo incluye trámites donde participó según el historial, además de los actualmente asignados, sin duplicar el total de trámites.

Los estados y las esperas corresponden a la situación actual de esa cohorte al generar el informe. No es un reporte de actuaciones ocurridas durante el período: un trámite iniciado antes del rango no se incluye aunque haya tenido actividad reciente.

## Indicadores y fuentes

- **Registrados / en curso / finalizados:** recuento único por trámite y su estado actual.
- **Recepción:** ingreso en una instancia del organismo → recepción confirmada. Usa las fechas de inicio y cierre de las etapas de recepción.
- **Respuesta:** recepción → cierre de la gestión. Factibilidad termina cuando se envía la respuesta; proyecto cuando EDESA lo previsa; COPAIPA y Secretaría cuando adjuntan el dictamen; ENRESP cuando adjunta la resolución; EDESA final cuando incorpora el contrato firmado.
- **Ciclo completo:** fecha de creación → fecha de conexión efectivamente registrada, sólo para finalizados con fechas válidas.
- **Mediana:** valor central de los tiempos válidos, para complementar el promedio cuando hay casos de duración elevada.

EDESA tiene tres instancias separadas: factibilidad, Proyecto Ejecutivo y contrato. Para el Proyecto Ejecutivo, el ingreso comienza en el evento `PROYECTO_ENVIADO`, con la fecha de carga del documento como alternativa; nunca en la fecha en que se solicitó al cliente. Para la recepción final de EDESA se toma el evento de auditoría `RECIBIDO` de `firma-contrato`, porque el inicio del historial corresponde a la llegada y no al acuse de recepción.

Los tiempos son **corridos**, no días hábiles ni dedicación de trabajo. La respuesta incluye las esperas dentro de la gestión, por ejemplo SMTP o la firma del titular. Las inspecciones y conexión están incluidas en el ciclo completo, no en el promedio de las seis instancias de recepción/respuesta. No se declara ningún plazo legal ni incumplimiento automático.

Cada indicador incluye cantidad de muestras. Una fecha ausente, invertida o posterior al corte se excluye del promedio correspondiente; nunca se convierte en una duración de cero. Un guion indica ausencia de muestras. Se informa la cantidad de gestiones con fechas insuficientes o inconsistentes. Los registros antiguos sin fechas suficientes se conservan; no se reconstruyen datos ficticios.

## Visualizaciones y pendientes

Las altas se agrupan por día hasta 31 días de rango, por semana hasta 120 y por mes para períodos mayores. Se incluyen los bloques sin altas. Los filtros de fechas se aplican antes de construir los gráficos, estados y tiempos.

Las esperas muestran hasta diez gestiones de la instancia actual con fecha suficiente, ordenadas por antigüedad. No se muestran como pendientes históricos incompletos de instancias que el trámite ya dejó atrás. Los períodos en espera del cliente no se atribuyen a recepción de EDESA.

## Exportación

CSV UTF-8 con BOM y separador `;` para facilitar su apertura en Excel. Conserva los filtros e incluye indicadores generales, tiempos por organismo, desglose por instancia, estados y bloques de altas. Los tiempos numéricos se exportan en días corridos con cuatro decimales. Los campos sin medición quedan vacíos.

La descarga es institucional, no se almacena en caché y no incluye códigos de acceso, NIS, DNI/CUIT, titulares ni direcciones de correo. Los nombres y siglas exportados se protegen contra interpretación como fórmulas de planilla. No requiere paquetes ni migraciones nuevas.

## Validación

`python manage.py test apps.reportes` comprueba promedios ponderados, medianas, múltiples intervenciones de EDESA, exclusión de esperas del cliente, fechas faltantes o futuras, fronteras de fecha local, permisos, filtros, exportación y consultas SQL sin crecimiento por cada trámite.

Las nuevas presentaciones conservan sus datos y se identifican por el nombre del titular. Los registros históricos mínimos siguen incluidos en recuentos y tiempos, identificados mediante su NIS. Los adjuntos iniciales sólo se remiten por correo a EDESA.

Las solicitudes observadas no se cuentan como respuestas pendientes del organismo mientras esperan al interesado. En factibilidad se descuentan los intervalos entre observación y subsanación del tiempo de respuesta y de la antigüedad de los pendientes, según la auditoría.

El filtro **Circuito** separa GGER (predeterminado) y obra de nexo. El total GGER cuenta una vez cada expediente, aunque tenga nexo. Los indicadores del nexo usan sus propias fechas, estados e historial desde la habilitación del proyecto; la factibilidad común sólo pertenece al GGER. El CSV incluye el circuito seleccionado y usa los mismos filtros del panel.
