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

    # V3: función objetivo de calidad dentro de cada escenario de días.
    peso_obj_prioridad_dia: int = 120
    peso_obj_dispersion_geografica: int = 2
    peso_obj_balance_dia: int = 20
    peso_obj_balance_auditor: int = 8
    peso_obj_inicio_temprano: int = 1
    peso_obj_supervisor_alternativo: int = 5

    # V3: métricas posteriores de calidad. Menor costo_operativo = mejor.
    peso_calidad_espera: float = 1.0
    peso_calidad_balance_dia: float = 0.35
    peso_calidad_balance_auditor: float = 0.25
    peso_calidad_cambio_acompanante: float = 20.0

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
