from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .config import OptimizationConfig
from .depot import DEPOT_ID
from .distance_matrix import TravelValue, travel_slots
from .models import PlanItem, TIPO_FISICA, VehicleLeg


DEFAULT_VEHICLE_CAPACITY = 4


@dataclass(frozen=True)
class VehiclePlanMetrics:
    legs: tuple[VehicleLeg, ...]
    vehicle_km: float
    vehicle_travel_min: float
    vehicle_trips: int
    vehicles_required_peak: int
    solo_legs: int
    shared_legs: int
    rendezvous_issues: int = 0


@dataclass(frozen=True)
class _PassengerLeg:
    auditor: str
    dia: int
    origen_id: str
    destino_id: str
    salida_slot: int
    llegada_slot: int
    motivo: str


def _travel_value(matrix: dict[tuple[str, str], TravelValue], origin: str, destination: str) -> TravelValue:
    return matrix.get((origin, destination), TravelValue(0.0, 0.0, 0.0))


def _auditor_sequences(plan: list[PlanItem]) -> dict[tuple[str, int], list[PlanItem]]:
    sequences: dict[tuple[str, int], list[PlanItem]] = defaultdict(list)
    for item in plan:
        sequences[(item.auditor_responsable, item.dia)].append(item)
        if item.auditor_acompanante:
            sequences[(item.auditor_acompanante, item.dia)].append(item)
    for values in sequences.values():
        values.sort(key=lambda x: (x.inicio_slot, x.fin_slot, x.obra_id))
    return sequences


def _base_passenger_legs(
    plan: list[PlanItem],
    matrix: dict[tuple[str, str], TravelValue],
    config: OptimizationConfig,
) -> tuple[list[_PassengerLeg], dict[tuple[str, int, str], _PassengerLeg]]:
    legs: list[_PassengerLeg] = []
    inbound: dict[tuple[str, int, str], _PassengerLeg] = {}
    for (auditor, day), items in _auditor_sequences(plan).items():
        previous_id = DEPOT_ID
        previous_end = 0
        for item in items:
            slots = travel_slots(matrix, previous_id, item.obra_id, config)
            if previous_id == DEPOT_ID:
                # Puede ser negativo: representa salida de ASEG antes de las 08:00.
                departure = item.inicio_slot - slots
            else:
                departure = previous_end
            arrival = departure + slots
            leg = _PassengerLeg(
                auditor=auditor,
                dia=day,
                origen_id=previous_id,
                destino_id=item.obra_id,
                salida_slot=departure,
                llegada_slot=arrival,
                motivo="Llegada a actividad",
            )
            legs.append(leg)
            inbound[(auditor, day, item.obra_id)] = leg
            previous_id = item.obra_id
            previous_end = item.fin_slot

        if items:
            slots = travel_slots(matrix, previous_id, DEPOT_ID, config)
            legs.append(
                _PassengerLeg(
                    auditor=auditor,
                    dia=day,
                    origen_id=previous_id,
                    destino_id=DEPOT_ID,
                    salida_slot=previous_end,
                    llegada_slot=previous_end + slots,
                    motivo="Regreso a ASEG",
                )
            )
    return legs, inbound


def _force_physical_pairs(
    plan: list[PlanItem],
    passenger_legs: list[_PassengerLeg],
    inbound: dict[tuple[str, int, str], _PassengerLeg],
    matrix: dict[tuple[str, str], TravelValue],
    config: OptimizationConfig,
) -> tuple[list[_PassengerLeg], int]:
    """Responsable y acompañante comparten el tramo final hacia la inspección física."""
    result = list(passenger_legs)
    issues = 0
    for item in plan:
        if item.tipo_revision != TIPO_FISICA or not item.auditor_acompanante:
            continue
        a = item.auditor_responsable
        b = item.auditor_acompanante
        la = inbound.get((a, item.dia, item.obra_id))
        lb = inbound.get((b, item.dia, item.obra_id))
        if la is None or lb is None:
            issues += 1
            continue
        if la.origen_id == lb.origen_id and la.salida_slot == lb.salida_slot:
            continue

        result = [leg for leg in result if leg not in (la, lb)]
        shared_slots = travel_slots(matrix, DEPOT_ID, item.obra_id, config)
        shared_departure = item.inicio_slot - shared_slots

        for original in (la, lb):
            if original.origen_id == DEPOT_ID:
                continue
            back_slots = travel_slots(matrix, original.origen_id, DEPOT_ID, config)
            back_departure = original.salida_slot
            back_arrival = back_departure + back_slots
            if back_arrival > shared_departure:
                issues += 1
            result.append(
                _PassengerLeg(
                    auditor=original.auditor,
                    dia=item.dia,
                    origen_id=original.origen_id,
                    destino_id=DEPOT_ID,
                    salida_slot=back_departure,
                    llegada_slot=back_arrival,
                    motivo="Reencuentro para inspección física",
                )
            )

        result.append(_PassengerLeg(a, item.dia, DEPOT_ID, item.obra_id, shared_departure, item.inicio_slot, f"Inspección física compartida con {b}"))
        result.append(_PassengerLeg(b, item.dia, DEPOT_ID, item.obra_id, shared_departure, item.inicio_slot, f"Inspección física compartida con {a}"))
    return result, issues


def _group_passenger_legs(
    legs: list[_PassengerLeg], matrix: dict[tuple[str, str], TravelValue], config: OptimizationConfig
) -> list[VehicleLeg]:
    groups: dict[tuple[int, str, str, int, int], list[_PassengerLeg]] = defaultdict(list)
    for leg in legs:
        groups[(leg.dia, leg.origen_id, leg.destino_id, leg.salida_slot, leg.llegada_slot)].append(leg)

    vehicle_legs: list[VehicleLeg] = []
    counter_by_day: dict[int, int] = defaultdict(int)
    capacity = max(1, int(getattr(config, "capacidad_vehiculo", DEFAULT_VEHICLE_CAPACITY)))
    for key in sorted(groups, key=lambda x: (x[0], x[3], x[1], x[2])):
        day, origin, destination, departure, arrival = key
        passengers = sorted({leg.auditor for leg in groups[key]})
        motives = sorted({leg.motivo for leg in groups[key]})
        value = _travel_value(matrix, origin, destination)
        for start in range(0, len(passengers), capacity):
            chunk = tuple(passengers[start : start + capacity])
            counter_by_day[day] += 1
            vehicle_legs.append(
                VehicleLeg(
                    dia=day,
                    vehicle_id=f"VIAJE-D{day}-{counter_by_day[day]:02d}",
                    origen_id=origin,
                    destino_id=destination,
                    salida_slot=departure,
                    llegada_slot=arrival,
                    pasajeros=chunk,
                    distancia_km=value.distancia_estimada_km,
                    tiempo_min=value.tiempo_estimado_min,
                    motivo=" / ".join(motives),
                )
            )
    return vehicle_legs


def _peak_concurrent(legs: list[VehicleLeg]) -> int:
    peak = 0
    by_day: dict[int, list[VehicleLeg]] = defaultdict(list)
    for leg in legs:
        by_day[leg.dia].append(leg)
    for day_legs in by_day.values():
        events: list[tuple[int, int]] = []
        for leg in day_legs:
            if leg.llegada_slot <= leg.salida_slot:
                continue
            events.append((leg.salida_slot, 1))
            events.append((leg.llegada_slot, -1))
        current = 0
        for _, delta in sorted(events, key=lambda e: (e[0], e[1])):
            current += delta
            peak = max(peak, current)
    return peak


def calculate_vehicle_plan(
    plan: list[PlanItem], matrix: dict[tuple[str, str], TravelValue], config: OptimizationConfig
) -> VehiclePlanMetrics:
    if not plan:
        return VehiclePlanMetrics((), 0.0, 0.0, 0, 0, 0, 0, 0)

    passenger_legs, inbound = _base_passenger_legs(plan, matrix, config)
    passenger_legs, rendezvous_issues = _force_physical_pairs(plan, passenger_legs, inbound, matrix, config)
    vehicle_legs = _group_passenger_legs(passenger_legs, matrix, config)
    km = sum(leg.distancia_km for leg in vehicle_legs)
    minutes = sum(leg.tiempo_min for leg in vehicle_legs)
    solo = sum(leg.ocupacion == 1 for leg in vehicle_legs if leg.distancia_km > 0)
    shared = sum(leg.ocupacion > 1 for leg in vehicle_legs if leg.distancia_km > 0)
    return VehiclePlanMetrics(
        legs=tuple(vehicle_legs),
        vehicle_km=km,
        vehicle_travel_min=minutes,
        vehicle_trips=len([leg for leg in vehicle_legs if leg.distancia_km > 0]),
        vehicles_required_peak=_peak_concurrent(vehicle_legs),
        solo_legs=solo,
        shared_legs=shared,
        rendezvous_issues=rendezvous_issues,
    )
