# OPTIMIZACION_INSPECCIONES

Motor de optimización para planear inspecciones físicas de obra pública.

El objetivo del proyecto es encontrar una planeación que coordine auditores,
supervisores municipales y contratistas, minimizando posteriormente días,
tiempos de traslado, distancias y tiempos muertos.

## Estado actual: V0

La primera versión utiliza **Google OR-Tools / CP-SAT** para responder:

> ¿Cuál es el menor número de días en el que puede programarse el conjunto
> completo de inspecciones respetando las reglas operativas básicas?

La V0 considera:

- auditor responsable obligatorio;
- mínimo dos auditores por inspección;
- parejas de auditores estables durante cada jornada;
- duración estimada de cada revisión;
- jornada laboral;
- supervisor municipal preferente o alternativo;
- imposibilidad de que un supervisor esté en dos obras simultáneamente;
- imposibilidad de que un contratista esté en dos obras simultáneamente;
- prioridad de 1 a 5.

**Todavía no se consideran traslados ni rutas en la V0.** Esa separación es
intencional: primero validamos el modelo de programación y después
incorporamos Google Routes y ALNS.

## Datos

`data/input/obras.csv` contiene las 44 inspecciones normalizadas a partir del
archivo de planeación.

Los proyectos ejecutivos que comparten coordenadas conservan esa ubicación:
corresponden a revisiones realizadas en la Dirección General de Obras
Públicas del municipio.

En obras con más de un supervisor:

- el primero es el preferente;
- cualquiera de los siguientes puede asistir como alternativa;
- no se requiere la presencia simultánea de todos.

## Ejecutarlo sin VS Code

Este repositorio incluye el workflow **Ejecutar modelo V0**.

En GitHub:

1. abre `Actions`;
2. selecciona `Ejecutar modelo V0`;
3. pulsa `Run workflow`;
4. define el rango de días y el tiempo máximo por escenario;
5. al terminar, descarga el artefacto `resultados-modelo-v0`.

El artefacto contiene un resumen JSON, el log de ejecución y, si se encuentra
solución, un CSV con el plan propuesto.

## Ejecución local opcional

```bash
pip install -r requirements.txt
python main.py
```

## Arquitectura

```text
data/input/
    obras.csv
    auditores.csv
    parametros.json

src/
    config.py
    data_loader.py
    models.py
    validator.py
    feasibility.py
    optimizer.py
    reporting.py
    distance_matrix.py

tests/
docs/
```

## Hoja de ruta

1. **V0 — Factibilidad:** CP-SAT, parejas, horarios, supervisor y contratista.
2. **V1 — Geografía:** matriz de distancias aproximadas entre obras.
3. **V2 — Red vial:** Google Routes para tiempos y kilómetros reales.
4. **V3 — Metaheurística:** ALNS para mejorar rutas, días y parejas.
5. **V4 — Visualización:** mapa, Gantt, indicadores y comparación de escenarios.

La formulación de la V0 se documenta en [`docs/MODELO_V0.md`](docs/MODELO_V0.md).
