# Resultado de ejecución V1 geográfica

Fecha de ejecución: 2026-09-05.

## Datos y supuestos

- 44 actividades.
- 14 auditores disponibles.
- 144.5 horas de revisión.
- Jornada modelada: 08:00–17:00.
- 17 proyectos documentales en la DGOP; no requieren acompañante.
- Inspecciones físicas: responsable + acompañante.
- Traslados incluidos para auditores, supervisores y contratistas.
- Distancia V1 = Haversine × 1.25.
- Velocidad media de referencia = 35 km/h.
- Intervalo temporal = 30 minutos; los traslados positivos se redondean hacia arriba al siguiente intervalo.

## Resultado mínimo

La cota inferior teórica es de 3 días. El modelo CP-SAT encontró una solución factible en 3 días aun incorporando los tiempos de traslado aproximados. Por tanto, bajo los supuestos V1, 3 días continúa siendo el mínimo factible certificado.

Resultado de la corrida de referencia:

- 3 días: FACTIBLE.
- Traslado aproximado de auditores: 275.3 km-auditor.
- Tiempo aproximado de traslado de auditores: 7.9 h-auditor.
- Traslado de supervisores: 48.2 km / 1.4 h.
- Traslado de contratistas: 15.9 km / 0.5 h.

## Escenarios de comparación

Se ejecutaron también escenarios forzados de 4 y 5 días:

| Días | Factibilidad | Km-auditor aprox. | Horas traslado auditor | Km supervisores | Km contratistas |
|---:|---|---:|---:|---:|---:|
| 3 | Factible | 275.3 | 7.9 | 48.2 | 15.9 |
| 4 | Factible | 245.6 | 7.0 | 43.5 | 25.0 |
| 5 | Factible | 252.2 | 7.2 | 55.5 | 0.0 |

## Interpretación y limitación

Estos kilómetros son métricas de las soluciones factibles encontradas, no mínimos globales de distancia. La función objetivo actual prioriza factibilidad, prioridad e inicios tempranos; el tiempo de viaje se usa como restricción dura, pero los kilómetros todavía no se minimizan de forma directa. Por ello, que el escenario de 5 días tenga más km-auditor que el de 4 días no significa que cinco días sean inherentemente peores: significa que CP-SAT encontró una solución válida diferente bajo la función objetivo vigente.

La conclusión robusta de la V1 es: **3 días siguen siendo operacionalmente factibles bajo una aproximación geográfica conservadora de los traslados**. La siguiente etapa debe reemplazar la aproximación por Google Routes y posteriormente incorporar una función objetivo/metaheurística que minimice explícitamente distancia, tiempo de viaje, espera y cambios de acompañante.
