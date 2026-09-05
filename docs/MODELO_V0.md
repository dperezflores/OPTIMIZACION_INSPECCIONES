# Modelo V0: factibilidad y programación

## Objetivo

Determinar el menor número de jornadas en el que puede programarse el
conjunto completo de inspecciones, antes de incorporar tiempos reales de
traslado.

## Recursos que sincroniza

Cada inspección requiere simultáneamente:

1. el auditor responsable de la obra;
2. un segundo auditor;
3. un supervisor municipal, cuando existe dato;
4. el contratista, cuando existe dato.

## Parejas

En la V0 las parejas son **estables por jornada**. Una pareja puede cambiar
al día siguiente, pero un auditor no puede tener dos compañeros distintos
durante el mismo día.

Esto representa el patrón operativo habitual: un auditor acompaña la obra
del otro y después se invierten los papeles.

## Supervisores

- El primer supervisor listado es el preferente.
- Los demás son alternativas válidas.
- Sólo uno debe asistir.
- Elegir un alternativo tiene una penalización suave en la función objetivo.
- `SIN DATO` no se transforma en un recurso compartido artificial.

## Contratistas

Un contratista no puede estar en dos inspecciones simultáneamente.

## Prioridad

La prioridad se captura de 1 a 5. El modelo penaliza más fuertemente mandar
a días posteriores las obras de prioridad alta.

## Tiempo

La jornada inicial se modela de 08:00 a 17:00, en intervalos de 30 minutos.
Si una duración no es múltiplo del intervalo, se redondea hacia arriba.

## Lo que todavía NO incorpora la V0

- tiempos de traslado entre obras;
- distancia vial;
- tráfico;
- ruta de supervisores;
- ruta de contratistas;
- ventanas particulares por persona;
- comida/pausas;
- ALNS.

Esas variables se incorporarán después de validar que la programación base
refleja correctamente la operación de auditoría.

## Evolución prevista

V0: CP-SAT para factibilidad y programación.

V1: matriz geográfica y distancias aproximadas.

V2: Google Routes para tiempo/distancia vial.

V3: ALNS para mejorar conjuntamente día, pareja, secuencia y ruta.

V4: interfaz de visualización, mapa, Gantt y comparación de escenarios.
