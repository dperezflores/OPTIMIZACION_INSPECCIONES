from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import math

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from .config import OptimizationConfig
from .depot import DEPOT_ID
from .distance_matrix import TravelValue, travel_slots
from .models import PlanItem, TIPO_FISICA, VehicleLeg


DEFAULT_VEHICLE_CAPACITY = 4
DEFAULT_MAX_INTERMEDIATE_WAIT_MIN = 90
DEFAULT_ROUTING_TIME_LIMIT_SECONDS = 2.0


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
class _TransportRequest:
    request_id: int
    auditor: str
    dia: int
    origen_id: str
    destino_id: str
    pickup_earliest_min: int
    pickup_latest_min: int
    dropoff_earliest_min: int
    dropoff_latest_min: int
    motivo: str
    destination_activity_id: str | None = None


@dataclass(frozen=True)
class _RoutingNode:
    location_id: str
    earliest_min: int
    latest_min: int
    demand: int
    request_id: int | None
    event: str | None
    auditor: str | None


@dataclass
class _SolvedRoutingDay:
    day: int
    manager: pywrapcp.RoutingIndexManager
    routing: pywrapcp.RoutingModel
    solution: pywrapcp.Assignment
    time_dimension: pywrapcp.RoutingDimension
    nodes: list[_RoutingNode]
    offset_min: int
    used_vehicles: int


@dataclass(frozen=True)
class _LegacyPassengerLeg:
    auditor: str
    dia: int
    origen_id: str
    destino_id: str
    salida_slot: int
    llegada_slot: int
    motivo: str


def _travel_value(matrix: dict[tuple[str, str], TravelValue], origin: str, destination: str) -> TravelValue:
    return matrix.get((origin, destination), TravelValue(0.0, 0.0, 0.0))


def _routing_minutes(
    matrix: dict[tuple[str, str], TravelValue],
    origin: str,
    destination: str,
    config: OptimizationConfig,
) -> int:
    return travel_slots(matrix, origin, destination, config) * config.slot_minutos


def _auditor_sequences(plan: list[PlanItem]) -> dict[tuple[str, int], list[PlanItem]]:
    sequences: dict[tuple[str, int], list[PlanItem]] = defaultdict(list)
    for item in plan:
        sequences[(item.auditor_responsable, item.dia)].append(item)
        if item.auditor_acompanante:
            sequences[(item.auditor_acompanante, item.dia)].append(item)
    for values in sequences.values():
        values.sort(key=lambda x: (x.inicio_slot, x.fin_slot, x.obra_id))
    return sequences


def _config_day_minutes(config: OptimizationConfig) -> int:
    try:
        return int(config.minutos_jornada)
    except (AttributeError, TypeError, ValueError):
        return 540


def _max_wait(config: OptimizationConfig) -> int:
    return max(
        0,
        int(getattr(config, "espera_maxima_parada_intermedia_min", DEFAULT_MAX_INTERMEDIATE_WAIT_MIN)),
    )


def _build_transport_requests(
    plan: list[PlanItem],
    matrix: dict[tuple[str, str], TravelValue],
    config: OptimizationConfig,
) -> tuple[dict[int, list[_TransportRequest]], dict[int, list[tuple[int, int]]], int]:
    """Convierte el calendario fijo en pickup/delivery sin mover actividades."""
    max_wait = _max_wait(config)
    by_day: dict[int, list[_TransportRequest]] = defaultdict(list)
    inbound_by_activity: dict[tuple[str, int, str], int] = {}
    next_id = 0

    for (auditor, day), items in _auditor_sequences(plan).items():
        previous_id = DEPOT_ID
        previous_end_min = 0
        for item in items:
            start_min = item.inicio_slot * config.slot_minutos
            if previous_id != item.obra_id:
                direct = _routing_minutes(matrix, previous_id, item.obra_id, config)
                if previous_id == DEPOT_ID:
                    pickup_latest = start_min - direct
                    pickup_earliest = pickup_latest - max_wait
                    dropoff_earliest = start_min - max_wait
                else:
                    pickup_earliest = previous_end_min
                    pickup_latest = min(previous_end_min + max_wait, start_min - direct)
                    dropoff_earliest = max(start_min - max_wait, pickup_earliest + direct)
                dropoff_latest = start_min
                pickup_latest = max(pickup_earliest, pickup_latest)
                dropoff_earliest = min(dropoff_latest, max(pickup_earliest + direct, dropoff_earliest))
                request = _TransportRequest(
                    next_id,
                    auditor,
                    day,
                    previous_id,
                    item.obra_id,
                    pickup_earliest,
                    pickup_latest,
                    dropoff_earliest,
                    dropoff_latest,
                    f"Llegada a {item.obra_id}",
                    item.obra_id,
                )
                by_day[day].append(request)
                inbound_by_activity[(auditor, day, item.obra_id)] = next_id
                next_id += 1
            previous_id = item.obra_id
            previous_end_min = item.fin_slot * config.slot_minutos

        if items and previous_id != DEPOT_ID:
            direct = _routing_minutes(matrix, previous_id, DEPOT_ID, config)
            pickup_earliest = previous_end_min
            pickup_latest = previous_end_min + max_wait
            by_day[day].append(
                _TransportRequest(
                    next_id,
                    auditor,
                    day,
                    previous_id,
                    DEPOT_ID,
                    pickup_earliest,
                    pickup_latest,
                    previous_end_min + direct,
                    pickup_latest + direct + max_wait,
                    "Regreso a ASEG",
                    None,
                )
            )
            next_id += 1

    physical_pairs: dict[int, list[tuple[int, int]]] = defaultdict(list)
    rendezvous_issues = 0
    for item in plan:
        if item.tipo_revision != TIPO_FISICA or not item.auditor_acompanante:
            continue
        a_req = inbound_by_activity.get((item.auditor_responsable, item.dia, item.obra_id))
        b_req = inbound_by_activity.get((item.auditor_acompanante, item.dia, item.obra_id))
        if a_req is None or b_req is None:
            if a_req != b_req:
                rendezvous_issues += 1
            continue
        physical_pairs[item.dia].append((a_req, b_req))
    return dict(by_day), dict(physical_pairs), rendezvous_issues


def _build_routing_model(
    *,
    day: int,
    requests: list[_TransportRequest],
    physical_pairs: list[tuple[int, int]],
    vehicle_count: int,
    matrix: dict[tuple[str, str], TravelValue],
    config: OptimizationConfig,
    optimize_distance: bool,
    time_limit_seconds: float,
) -> _SolvedRoutingDay | None:
    if not requests:
        return None

    capacity = max(1, int(getattr(config, "capacidad_vehiculo", DEFAULT_VEHICLE_CAPACITY)))
    max_wait = _max_wait(config)
    nodes: list[_RoutingNode] = [
        _RoutingNode(DEPOT_ID, 0, _config_day_minutes(config) + 4 * max_wait, 0, None, None, None)
    ]
    pickup_node: dict[int, int] = {}
    delivery_node: dict[int, int] = {}
    for request in requests:
        pickup_node[request.request_id] = len(nodes)
        nodes.append(
            _RoutingNode(
                request.origen_id,
                request.pickup_earliest_min,
                request.pickup_latest_min,
                +1,
                request.request_id,
                "pickup",
                request.auditor,
            )
        )
        delivery_node[request.request_id] = len(nodes)
        nodes.append(
            _RoutingNode(
                request.destino_id,
                request.dropoff_earliest_min,
                request.dropoff_latest_min,
                -1,
                request.request_id,
                "delivery",
                request.auditor,
            )
        )

    min_time = min(node.earliest_min for node in nodes[1:])
    max_time = max(node.latest_min for node in nodes[1:])
    offset = max(0, -min_time) + max_wait
    horizon = max_time + offset + max_wait * 3 + _config_day_minutes(config)

    manager = pywrapcp.RoutingIndexManager(len(nodes), vehicle_count, 0)
    routing = pywrapcp.RoutingModel(manager)

    def time_callback(from_index: int, to_index: int) -> int:
        origin = nodes[manager.IndexToNode(from_index)].location_id
        destination = nodes[manager.IndexToNode(to_index)].location_id
        return _routing_minutes(matrix, origin, destination, config)

    time_index = routing.RegisterTransitCallback(time_callback)
    # El vehículo puede permanecer estacionado durante una actividad completa.
    # El límite de espera de 90 min corresponde al PASAJERO antes de ser recogido,
    # y ya está expresado en las ventanas pickup_earliest/pickup_latest.
    routing.AddDimension(time_index, max(1, horizon), max(1, horizon), False, "Time")
    time_dimension = routing.GetDimensionOrDie("Time")
    for node_id, node in enumerate(nodes[1:], start=1):
        index = manager.NodeToIndex(node_id)
        time_dimension.CumulVar(index).SetRange(node.earliest_min + offset, node.latest_min + offset)
    for vehicle in range(vehicle_count):
        time_dimension.CumulVar(routing.Start(vehicle)).SetRange(0, horizon)
        time_dimension.CumulVar(routing.End(vehicle)).SetRange(0, horizon)

    demand_index = routing.RegisterUnaryTransitCallback(lambda index: nodes[manager.IndexToNode(index)].demand)
    routing.AddDimensionWithVehicleCapacity(demand_index, 0, [capacity] * vehicle_count, True, "Capacity")

    solver = routing.solver()
    for request in requests:
        pickup = manager.NodeToIndex(pickup_node[request.request_id])
        delivery = manager.NodeToIndex(delivery_node[request.request_id])
        routing.AddPickupAndDelivery(pickup, delivery)
        solver.Add(routing.VehicleVar(pickup) == routing.VehicleVar(delivery))
        solver.Add(time_dimension.CumulVar(pickup) <= time_dimension.CumulVar(delivery))

    for request_a, request_b in physical_pairs:
        if request_a in pickup_node and request_b in pickup_node:
            solver.Add(
                routing.VehicleVar(manager.NodeToIndex(pickup_node[request_a]))
                == routing.VehicleVar(manager.NodeToIndex(pickup_node[request_b]))
            )

    # Incluso en la fase de factibilidad damos al constructor una señal de costo.
    # El número de vehículos sigue siendo lexicográfico: k se fija externamente y
    # se prueba estrictamente 1, 2, 3... antes de optimizar km/tiempo con ese k.
    def route_cost(from_index: int, to_index: int) -> int:
        origin = nodes[manager.IndexToNode(from_index)].location_id
        destination = nodes[manager.IndexToNode(to_index)].location_id
        value = _travel_value(matrix, origin, destination)
        return int(round(value.distancia_estimada_km * 1000.0)) + int(round(value.tiempo_estimado_min * 10.0))

    cost_index = routing.RegisterTransitCallback(route_cost)
    routing.SetArcCostEvaluatorOfAllVehicles(cost_index)

    search = pywrapcp.DefaultRoutingSearchParameters()
    search.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION
    if optimize_distance:
        search.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    search.time_limit.FromMilliseconds(max(100, int(max(0.1, time_limit_seconds) * 1000)))

    solution = routing.SolveWithParameters(search)
    if solution is None:
        return None
    used = sum(1 for vehicle in range(vehicle_count) if routing.IsVehicleUsed(solution, vehicle))
    return _SolvedRoutingDay(day, manager, routing, solution, time_dimension, nodes, offset, used)


def _solve_day_lexicographic(
    *,
    day: int,
    requests: list[_TransportRequest],
    physical_pairs: list[tuple[int, int]],
    matrix: dict[tuple[str, str], TravelValue],
    config: OptimizationConfig,
) -> _SolvedRoutingDay | None:
    if not requests:
        return None

    upper = max(1, len({request.auditor for request in requests}))
    total_budget = max(
        0.5,
        float(getattr(config, "vehicle_routing_time_limit_seconds", DEFAULT_ROUTING_TIME_LIMIT_SECONDS)),
    )
    feasibility_budget = max(0.25, min(0.75, total_budget * 0.40))

    feasible: _SolvedRoutingDay | None = None
    minimum_vehicles: int | None = None
    for vehicle_count in range(1, upper + 1):
        candidate = _build_routing_model(
            day=day,
            requests=requests,
            physical_pairs=physical_pairs,
            vehicle_count=vehicle_count,
            matrix=matrix,
            config=config,
            optimize_distance=False,
            time_limit_seconds=feasibility_budget,
        )
        if candidate is not None:
            minimum_vehicles = max(1, candidate.used_vehicles)
            feasible = candidate
            break

    if feasible is None or minimum_vehicles is None:
        return None

    optimized = _build_routing_model(
        day=day,
        requests=requests,
        physical_pairs=physical_pairs,
        vehicle_count=minimum_vehicles,
        matrix=matrix,
        config=config,
        optimize_distance=True,
        time_limit_seconds=max(0.3, total_budget),
    )
    return optimized or feasible


def _extract_vehicle_legs(
    solved: _SolvedRoutingDay,
    matrix: dict[tuple[str, str], TravelValue],
    config: OptimizationConfig,
) -> list[VehicleLeg]:
    result: list[VehicleLeg] = []
    route_number = 0
    for vehicle in range(solved.routing.vehicles()):
        if not solved.routing.IsVehicleUsed(solved.solution, vehicle):
            continue
        route_number += 1
        vehicle_id = f"VEH-D{solved.day}-{route_number:02d}"
        passengers: set[str] = set()
        index = solved.routing.Start(vehicle)
        while not solved.routing.IsEnd(index):
            node = solved.nodes[solved.manager.IndexToNode(index)]
            if node.event == "pickup" and node.auditor:
                passengers.add(node.auditor)
            elif node.event == "delivery" and node.auditor:
                passengers.discard(node.auditor)

            next_index = solved.solution.Value(solved.routing.NextVar(index))
            next_node = solved.nodes[solved.manager.IndexToNode(next_index)]
            origin = node.location_id
            destination = next_node.location_id
            value = _travel_value(matrix, origin, destination)
            transit_min = _routing_minutes(matrix, origin, destination, config)
            if origin != destination and (value.distancia_estimada_km > 0 or transit_min > 0):
                arrival_shifted = solved.solution.Value(solved.time_dimension.CumulVar(next_index))
                departure_min = arrival_shifted - transit_min - solved.offset_min
                arrival_min = arrival_shifted - solved.offset_min
                motive = "Ruta compartida optimizada"
                if next_node.event == "pickup" and next_node.auditor:
                    motive = f"Recoger a {next_node.auditor}"
                elif next_node.event == "delivery" and next_node.auditor:
                    motive = f"Dejar a {next_node.auditor}"
                result.append(
                    VehicleLeg(
                        dia=solved.day,
                        vehicle_id=vehicle_id,
                        origen_id=origin,
                        destino_id=destination,
                        salida_slot=math.floor(departure_min / config.slot_minutos),
                        llegada_slot=math.ceil(arrival_min / config.slot_minutos),
                        pasajeros=tuple(sorted(passengers)),
                        distancia_km=value.distancia_estimada_km,
                        tiempo_min=value.tiempo_estimado_min,
                        motivo=motive,
                    )
                )
            index = next_index
    return result


# --- Referencia del agrupador V5 anterior: sólo fallback y benchmark CI. ---

def _legacy_passenger_legs(
    plan: list[PlanItem], matrix: dict[tuple[str, str], TravelValue], config: OptimizationConfig
) -> tuple[list[_LegacyPassengerLeg], dict[tuple[str, int, str], _LegacyPassengerLeg]]:
    legs: list[_LegacyPassengerLeg] = []
    inbound: dict[tuple[str, int, str], _LegacyPassengerLeg] = {}
    for (auditor, day), items in _auditor_sequences(plan).items():
        previous_id = DEPOT_ID
        previous_end = 0
        for item in items:
            slots = travel_slots(matrix, previous_id, item.obra_id, config)
            departure = item.inicio_slot - slots if previous_id == DEPOT_ID else previous_end
            leg = _LegacyPassengerLeg(auditor, day, previous_id, item.obra_id, departure, departure + slots, "Llegada a actividad")
            legs.append(leg)
            inbound[(auditor, day, item.obra_id)] = leg
            previous_id = item.obra_id
            previous_end = item.fin_slot
        if items:
            slots = travel_slots(matrix, previous_id, DEPOT_ID, config)
            legs.append(_LegacyPassengerLeg(auditor, day, previous_id, DEPOT_ID, previous_end, previous_end + slots, "Regreso a ASEG"))
    return legs, inbound


def _legacy_force_physical_pairs(
    plan: list[PlanItem],
    legs: list[_LegacyPassengerLeg],
    inbound: dict[tuple[str, int, str], _LegacyPassengerLeg],
    matrix: dict[tuple[str, str], TravelValue],
    config: OptimizationConfig,
) -> tuple[list[_LegacyPassengerLeg], int]:
    result = list(legs)
    issues = 0
    for item in plan:
        if item.tipo_revision != TIPO_FISICA or not item.auditor_acompanante:
            continue
        la = inbound.get((item.auditor_responsable, item.dia, item.obra_id))
        lb = inbound.get((item.auditor_acompanante, item.dia, item.obra_id))
        if la is None or lb is None:
            issues += 1
            continue
        if la.origen_id == lb.origen_id and la.salida_slot == lb.salida_slot:
            continue
        result = [leg for leg in result if leg not in (la, lb)]
        shared_slots = travel_slots(matrix, DEPOT_ID, item.obra_id, config)
        shared_departure = item.inicio_slot - shared_slots
        for original in (la, lb):
            if original.origen_id != DEPOT_ID:
                back_slots = travel_slots(matrix, original.origen_id, DEPOT_ID, config)
                result.append(_LegacyPassengerLeg(original.auditor, item.dia, original.origen_id, DEPOT_ID, original.salida_slot, original.salida_slot + back_slots, "Reencuentro"))
        result.append(_LegacyPassengerLeg(item.auditor_responsable, item.dia, DEPOT_ID, item.obra_id, shared_departure, item.inicio_slot, "Inspección física compartida"))
        result.append(_LegacyPassengerLeg(item.auditor_acompanante, item.dia, DEPOT_ID, item.obra_id, shared_departure, item.inicio_slot, "Inspección física compartida"))
    return result, issues


def _legacy_group(
    legs: list[_LegacyPassengerLeg], matrix: dict[tuple[str, str], TravelValue], config: OptimizationConfig
) -> list[VehicleLeg]:
    groups: dict[tuple[int, str, str, int, int], list[_LegacyPassengerLeg]] = defaultdict(list)
    for leg in legs:
        groups[(leg.dia, leg.origen_id, leg.destino_id, leg.salida_slot, leg.llegada_slot)].append(leg)
    result: list[VehicleLeg] = []
    counter: dict[int, int] = defaultdict(int)
    capacity = max(1, int(getattr(config, "capacidad_vehiculo", DEFAULT_VEHICLE_CAPACITY)))
    for key in sorted(groups, key=lambda x: (x[0], x[3], x[1], x[2])):
        day, origin, destination, departure, arrival = key
        passengers = sorted({leg.auditor for leg in groups[key]})
        value = _travel_value(matrix, origin, destination)
        for start in range(0, len(passengers), capacity):
            counter[day] += 1
            result.append(
                VehicleLeg(
                    day,
                    f"LEGACY-D{day}-{counter[day]:02d}",
                    origin,
                    destination,
                    departure,
                    arrival,
                    tuple(passengers[start : start + capacity]),
                    value.distancia_estimada_km,
                    value.tiempo_estimado_min,
                    "Agrupación exacta histórica",
                )
            )
    return result


def _legacy_peak(legs: list[VehicleLeg]) -> int:
    peak = 0
    by_day: dict[int, list[VehicleLeg]] = defaultdict(list)
    for leg in legs:
        by_day[leg.dia].append(leg)
    for day_legs in by_day.values():
        events: list[tuple[int, int]] = []
        for leg in day_legs:
            if leg.llegada_slot > leg.salida_slot:
                events.extend(((leg.salida_slot, 1), (leg.llegada_slot, -1)))
        current = 0
        for _, delta in sorted(events, key=lambda event: (event[0], event[1])):
            current += delta
            peak = max(peak, current)
    return peak


def calculate_legacy_vehicle_plan(
    plan: list[PlanItem], matrix: dict[tuple[str, str], TravelValue], config: OptimizationConfig
) -> VehiclePlanMetrics:
    if not plan:
        return VehiclePlanMetrics((), 0.0, 0.0, 0, 0, 0, 0, 0)
    passenger_legs, inbound = _legacy_passenger_legs(plan, matrix, config)
    passenger_legs, issues = _legacy_force_physical_pairs(plan, passenger_legs, inbound, matrix, config)
    vehicle_legs = _legacy_group(passenger_legs, matrix, config)
    positive = [leg for leg in vehicle_legs if leg.distancia_km > 0]
    return VehiclePlanMetrics(
        tuple(vehicle_legs),
        sum(leg.distancia_km for leg in vehicle_legs),
        sum(leg.tiempo_min for leg in vehicle_legs),
        len(positive),
        _legacy_peak(vehicle_legs),
        sum(leg.ocupacion == 1 for leg in positive),
        sum(leg.ocupacion > 1 for leg in positive),
        issues,
    )


def calculate_vehicle_plan(
    plan: list[PlanItem], matrix: dict[tuple[str, str], TravelValue], config: OptimizationConfig
) -> VehiclePlanMetrics:
    if not plan:
        return VehiclePlanMetrics((), 0.0, 0.0, 0, 0, 0, 0, 0)

    requests_by_day, pairs_by_day, rendezvous_issues = _build_transport_requests(plan, matrix, config)
    vehicle_legs: list[VehicleLeg] = []
    vehicles_by_day: dict[int, int] = {}
    for day in sorted(requests_by_day):
        solved = _solve_day_lexicographic(
            day=day,
            requests=requests_by_day[day],
            physical_pairs=pairs_by_day.get(day, []),
            matrix=matrix,
            config=config,
        )
        if solved is None:
            legacy = calculate_legacy_vehicle_plan([item for item in plan if item.dia == day], matrix, config)
            vehicle_legs.extend(legacy.legs)
            vehicles_by_day[day] = legacy.vehicles_required_peak
            rendezvous_issues += max(1, legacy.rendezvous_issues)
            continue
        vehicle_legs.extend(_extract_vehicle_legs(solved, matrix, config))
        vehicles_by_day[day] = solved.used_vehicles

    positive = [leg for leg in vehicle_legs if leg.distancia_km > 0]
    return VehiclePlanMetrics(
        legs=tuple(sorted(vehicle_legs, key=lambda leg: (leg.dia, leg.vehicle_id, leg.salida_slot, leg.destino_id))),
        vehicle_km=sum(leg.distancia_km for leg in vehicle_legs),
        vehicle_travel_min=sum(leg.tiempo_min for leg in vehicle_legs),
        vehicle_trips=len(positive),
        vehicles_required_peak=max(vehicles_by_day.values(), default=0),
        solo_legs=sum(leg.ocupacion == 1 for leg in positive),
        shared_legs=sum(leg.ocupacion > 1 for leg in positive),
        rendezvous_issues=rendezvous_issues,
    )
