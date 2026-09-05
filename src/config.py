from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import math


def _parse_hhmm(value: str) -> datetime:
    return datetime.strptime(value, "%H:%M")


@dataclass(frozen=True)
class OptimizationConfig:
    hora_inicio: str = "08:00"
    hora_fin: str = "17:00"
    slot_minutos: int = 30
    dias_min: int = 2
    dias_max: int = 6
    time_limit_seconds: float = 30.0
    num_search_workers: int = 8
    prioridad_default: int = 3
    modo_parejas: str = "dinamicas_por_inspeccion"

    # V1 geográfica. Haversine se ajusta para aproximar recorrido vial.
    incluir_traslados: bool = True
    factor_distancia_vial: float = 1.25
    velocidad_promedio_kmh: float = 35.0
    penalizacion_geografica: int = 1

    # V3/V5: función objetivo de calidad dentro de cada escenario de días.
    # La prioridad se aplica CENTRADA respecto al promedio del lote: una obra con
    # prioridad promedio no recibe empuje hacia el día 1. El peso de prioridad es
    # razonable cuando está aproximadamente entre 0.5x y 1.5x el peso de balance
    # diario; valores mucho mayores vuelven a amontonar obras tempranamente.
    peso_obj_prioridad_dia: int = 30
    peso_obj_dispersion_geografica: int = 2

    # Balance diario debe ser del mismo orden que prioridad. Un rango práctico es
    # 0.7x-2.0x peso_obj_prioridad_dia: por debajo suele tolerar jornadas muy
    # desiguales; muy por encima puede sacrificar prioridad/geografía por simetría.
    peso_obj_balance_dia: int = 40

    # Balance entre auditores es secundario respecto al balance entre días porque
    # cada auditor ya tiene distinta carga responsable. Un rango razonable es
    # 0.25x-0.75x peso_obj_balance_dia.
    peso_obj_balance_auditor: int = 15
    peso_obj_inicio_temprano: int = 1
    peso_obj_supervisor_alternativo: int = 5

    # V3/V4: métricas posteriores de calidad. Menor costo_operativo = mejor.
    peso_calidad_traslado_auditor: float = 1.0
    peso_calidad_traslado_supervisor: float = 0.4
    peso_calidad_traslado_contratista: float = 0.4
    peso_calidad_espera: float = 1.0
    peso_calidad_balance_dia: float = 0.35
    peso_calidad_balance_auditor: float = 0.25
    peso_calidad_cambio_acompanante: float = 20.0

    # V5: flota suficiente, pero se favorece compartir cuando es compatible.
    capacidad_vehiculo: int = 4
    peso_calidad_km_vehiculo: float = 1.5
    peso_calidad_viaje_solo: float = 12.0
    peso_calidad_viaje_vehicular: float = 2.0

    # Máximo que un auditor puede quedar esperando en una parada intermedia después
    # de terminar una actividad para ser recogido por un vehículo compartido.
    espera_maxima_parada_intermedia_min: int = 90

    # Presupuesto de cómputo del subproblema vehicular POR DÍA. El ruteo primero
    # busca el mínimo número de vehículos y después minimiza distancia/tiempo.
    vehicle_routing_time_limit_seconds: float = 2.0

    # La ventana 08:00-17:00 sigue siendo la ventana de actividades. Los traslados
    # desde/hacia ASEG pueden extenderla y se penalizan para que sólo ocurra cuando
    # sea necesario (p. ej., revisiones de 8-8.5 h).
    peso_calidad_tiempo_adicional: float = 3.0

    @property
    def minutos_jornada(self) -> int:
        inicio = _parse_hhmm(self.hora_inicio)
        fin = _parse_hhmm(self.hora_fin)
        minutos = int((fin - inicio).total_seconds() // 60)
        if minutos <= 0:
            raise ValueError("hora_fin debe ser posterior a hora_inicio.")
        return minutos

    @property
    def slots_por_dia(self) -> int:
        if self.slot_minutos <= 0:
            raise ValueError("slot_minutos debe ser mayor que cero.")
        if self.minutos_jornada % self.slot_minutos != 0:
            raise ValueError("La jornada debe ser divisible exactamente entre slot_minutos.")
        return self.minutos_jornada // self.slot_minutos

    def minutos_a_slots(self, minutos: int) -> int:
        return max(1, math.ceil(minutos / self.slot_minutos))

    def traslado_minutos_a_slots(self, minutos: float) -> int:
        if minutos <= 0:
            return 0
        return math.ceil(minutos / self.slot_minutos)

    def slot_a_hora(self, slot: int) -> str:
        base = _parse_hhmm(self.hora_inicio)
        value = base + timedelta(minutes=slot * self.slot_minutos)
        return value.strftime("%H:%M")
