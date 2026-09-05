from __future__ import annotations

from collections import defaultdict
from typing import Optional

from ortools.sat.python import cp_model

from .config import OptimizationConfig
from .depot import DEPOT_ID
from .distance_matrix import TravelValue, build_travel_matrix, calculate_plan_travel_metrics, travel_slots
from .models import Auditor, Obra, PlanItem, ScenarioResult
from .quality import calculate_quality_metrics
from .vehicle_planner import calculate_vehicle_plan


class FeasibilitySolver:
    """CP-SAT con restricciones duras y función de calidad V3/V4/V5.

    V5 añade el depósito ASEG: todo auditor debe poder salir de ASEG, completar su
    agenda y regresar dentro de la jornada. La flota es suficiente; el uso compartido
    se evalúa después como criterio de calidad y se refina mediante ALNS.
    """

    def __init__(
        self,
        obras: list[Obra],
        auditores: list[Auditor],
        config: OptimizationConfig,
        travel_matrix: dict[tuple[str, str], TravelValue] | None = None,
    ) -> None:
        self.obras = obras
        self.auditores = [a for a in auditores if a.disponible]
        self.config = config
        self.auditor_ids = sorted(a.auditor_id for a in self.auditores)
        self.travel_matrix = travel_matrix if travel_matrix is not None else build_travel_matrix(obras, config)

    def _add_resource_travel_constraints(
        self,
        model: cp_model.CpModel,
        resource_items: dict[tuple[str, int], list[tuple[Obra, cp_model.IntVar, int, cp_model.IntVar]]],
    ) -> None:
        for (resource_id, day), items in resource_items.items():
            if len(items) < 2:
                continue
            for i in range(len(items)):
                obra_i, start_i, dur_i, present_i = items[i]
                for j in range(i + 1, len(items)):
                    obra_j, start_j, dur_j, present_j = items[j]
                    order_ij = model.new_bool_var(
                        f"ord__{resource_id}__d{day}__{obra_i.obra_id}__{obra_j.obra_id}"
                    )
                    tij = travel_slots(self.travel_matrix, obra_i.obra_id, obra_j.obra_id, self.config)
                    tji = travel_slots(self.travel_matrix, obra_j.obra_id, obra_i.obra_id, self.config)
                    model.add(start_j >= start_i + dur_i + tij).only_enforce_if(
                        [present_i, present_j, order_ij]
                    )
                    model.add(start_i >= start_j + dur_j + tji).only_enforce_if(
                        [present_i, present_j, order_ij.Not()]
                    )

    def _add_depot_constraints(
        self,
        model: cp_model.CpModel,
        auditor_items: dict[tuple[str, int], list[tuple[Obra, cp_model.IntVar, int, cp_model.IntVar]]],
    ) -> None:
        """Toda actividad de auditor debe quedar dentro de una jornada que puede iniciar y cerrar en ASEG."""
        horizon = self.config.slots_por_dia
        for (_auditor_id, _day), items in auditor_items.items():
            for obra, start, duration, present in items:
                outbound = travel_slots(self.travel_matrix, DEPOT_ID, obra.obra_id, self.config)
                inbound = travel_slots(self.travel_matrix, obra.obra_id, DEPOT_ID, self.config)
                model.add(start >= outbound).only_enforce_if(present)
                model.add(start + duration + inbound <= horizon).only_enforce_if(present)

    def _add_geographic_dispersion_objective(
        self,
        model: cp_model.CpModel,
        assign: dict[tuple[str, int], cp_model.IntVar],
        days: range,
        objective_terms: list,
    ) -> None:
        weight = self.config.peso_obj_dispersion_geografica
        if weight <= 0:
            return
        for i in range(len(self.obras)):
            obra_i = self.obras[i]
            for j in range(i + 1, len(self.obras)):
                obra_j = self.obras[j]
                vij = self.travel_matrix.get((obra_i.obra_id, obra_j.obra_id))
                vji = self.travel_matrix.get((obra_j.obra_id, obra_i.obra_id))
                distances = [v.distancia_estimada_km for v in (vij, vji) if v is not None]
                if not distances:
                    continue
                distance_tenths = max(0, round((sum(distances) / len(distances)) * 10))
                if distance_tenths == 0:
                    continue
                for d in days:
                    same_day = model.new_bool_var(
                        f"same_day__{obra_i.obra_id}__{obra_j.obra_id}__d{d}"
                    )
                    yi = assign[(obra_i.obra_id, d)]
                    yj = assign[(obra_j.obra_id, d)]
                    model.add(same_day <= yi)
                    model.add(same_day <= yj)
                    model.add(same_day >= yi + yj - 1)
                    objective_terms.append(weight * distance_tenths * same_day)

    def _add_balance_objective(self, model, auditor_items, days: range, objective_terms: list) -> None:
        max_possible = len(self.obras) * self.config.slots_por_dia * 2
        day_load_vars = []
        for d in days:
            terms = []
            for (_auditor_id, day), items in auditor_items.items():
                if day == d:
                    terms.extend(duration * present for _, _, duration, present in items)
            load = model.new_int_var(0, max_possible, f"day_auditor_load__d{d}")
            model.add(load == (sum(terms) if terms else 0))
            day_load_vars.append(load)
        if len(day_load_vars) > 1:
            day_max = model.new_int_var(0, max_possible, "day_load_max")
            day_min = model.new_int_var(0, max_possible, "day_load_min")
            model.add_max_equality(day_max, day_load_vars)
            model.add_min_equality(day_min, day_load_vars)
            day_span = model.new_int_var(0, max_possible, "day_load_span")
            model.add(day_span == day_max - day_min)
            objective_terms.append(self.config.peso_obj_balance_dia * day_span)

        auditor_load_vars = []
        for auditor_id in self.auditor_ids:
            terms = []
            for (resource_id, _day), items in auditor_items.items():
                if resource_id == auditor_id:
                    terms.extend(duration * present for _, _, duration, present in items)
            load = model.new_int_var(0, max_possible, f"auditor_load__{auditor_id}")
            model.add(load == (sum(terms) if terms else 0))
            auditor_load_vars.append(load)
        if len(auditor_load_vars) > 1:
            auditor_max = model.new_int_var(0, max_possible, "auditor_load_max")
            auditor_min = model.new_int_var(0, max_possible, "auditor_load_min")
            model.add_max_equality(auditor_max, auditor_load_vars)
            model.add_min_equality(auditor_min, auditor_load_vars)
            auditor_span = model.new_int_var(0, max_possible, "auditor_load_span")
            model.add(auditor_span == auditor_max - auditor_min)
            objective_terms.append(self.config.peso_obj_balance_auditor * auditor_span)

    def solve(
        self,
        dias: int,
        *,
        fixed_days: dict[str, int] | None = None,
        random_seed: int = 42,
    ) -> ScenarioResult:
        fixed_days = fixed_days or {}
        invalid = {obra_id: day for obra_id, day in fixed_days.items() if day < 1 or day > dias}
        if invalid:
            raise ValueError(f"Días fijados fuera del escenario de {dias} día(s): {invalid}")

        model = cp_model.CpModel()
        horizon = self.config.slots_por_dia
        days = range(dias)
        assign = {}
        start = {}
        companion = {}
        supervisor_choice = {}
        auditor_items = defaultdict(list)
        contractor_items = defaultdict(list)
        supervisor_items = defaultdict(list)
        objective_terms = []

        for obra in self.obras:
            obra_key = obra.obra_id
            duration = self.config.minutos_a_slots(obra.duracion_minutos)
            day_vars = []
            for d in days:
                y = model.new_bool_var(f"obra__{obra_key}__d{d}")
                assign[(obra_key, d)] = y
                day_vars.append(y)
                if obra_key in fixed_days:
                    model.add(y == (1 if fixed_days[obra_key] == d + 1 else 0))

                max_start = max(0, horizon - duration)
                s = model.new_int_var(0, max_start, f"start__{obra_key}__d{d}")
                start[(obra_key, d)] = s
                if duration > horizon:
                    model.add(y == 0)
                else:
                    model.add(s <= max_start * y)

                auditor_items[(obra.auditor_responsable, d)].append((obra, s, duration, y))
                if obra.requiere_acompanante:
                    companion_vars = []
                    for auditor_id in self.auditor_ids:
                        if auditor_id == obra.auditor_responsable:
                            continue
                        x = model.new_bool_var(f"comp__{obra_key}__{auditor_id}__d{d}")
                        companion[(obra_key, d, auditor_id)] = x
                        companion_vars.append(x)
                        auditor_items[(auditor_id, d)].append((obra, s, duration, x))
                    model.add(sum(companion_vars) == y)

                if obra.contratista_id:
                    contractor_items[(obra.contratista_id, d)].append((obra, s, duration, y))

                candidates = obra.supervisores_candidatos
                if candidates:
                    z_vars = []
                    for index, supervisor_id in enumerate(candidates):
                        z = model.new_bool_var(f"sup__{obra_key}__{supervisor_id}__d{d}")
                        supervisor_choice[(obra_key, d, supervisor_id)] = z
                        z_vars.append(z)
                        supervisor_items[(supervisor_id, d)].append((obra, s, duration, z))
                        if index > 0:
                            objective_terms.append(self.config.peso_obj_supervisor_alternativo * z)
                    model.add(sum(z_vars) == y)

                objective_terms.append((d * obra.prioridad * self.config.peso_obj_prioridad_dia) * y)
                objective_terms.append(self.config.peso_obj_inicio_temprano * s)
            model.add_exactly_one(day_vars)

        self._add_resource_travel_constraints(model, auditor_items)
        self._add_resource_travel_constraints(model, contractor_items)
        self._add_resource_travel_constraints(model, supervisor_items)
        self._add_depot_constraints(model, auditor_items)
        self._add_geographic_dispersion_objective(model, assign, days, objective_terms)
        self._add_balance_objective(model, auditor_items, days, objective_terms)
        model.minimize(sum(objective_terms))

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.config.time_limit_seconds
        solver.parameters.num_search_workers = self.config.num_search_workers
        solver.parameters.random_seed = int(random_seed)
        status = solver.solve(model)
        status_name = solver.status_name(status).upper()
        factible = status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
        result = ScenarioResult(
            dias=dias,
            status=status_name,
            factible=factible,
            wall_time_seconds=solver.wall_time,
            objective_value=solver.objective_value if factible else None,
            plan=[],
        )
        if not factible:
            return result

        plan: list[PlanItem] = []
        for obra in self.obras:
            for d in days:
                if solver.value(assign[(obra.obra_id, d)]) != 1:
                    continue
                start_slot = solver.value(start[(obra.obra_id, d)])
                duration = self.config.minutos_a_slots(obra.duracion_minutos)
                companero: Optional[str] = None
                if obra.requiere_acompanante:
                    for auditor_id in self.auditor_ids:
                        if auditor_id == obra.auditor_responsable:
                            continue
                        var = companion.get((obra.obra_id, d, auditor_id))
                        if var is not None and solver.value(var) == 1:
                            companero = auditor_id
                            break
                selected_supervisor: Optional[str] = None
                for supervisor_id in obra.supervisores_candidatos:
                    var = supervisor_choice.get((obra.obra_id, d, supervisor_id))
                    if var is not None and solver.value(var) == 1:
                        selected_supervisor = supervisor_id
                        break
                plan.append(
                    PlanItem(
                        obra_id=obra.obra_id,
                        contrato=obra.contrato,
                        descripcion=obra.descripcion,
                        dia=d + 1,
                        inicio_slot=start_slot,
                        fin_slot=start_slot + duration,
                        auditor_responsable=obra.auditor_responsable,
                        auditor_acompanante=companero,
                        supervisor_seleccionado=selected_supervisor,
                        contratista_id=obra.contratista_id,
                        prioridad=obra.prioridad,
                        tipo_revision=obra.tipo_revision,
                    )
                )

        result.plan = sorted(plan, key=lambda item: (item.dia, item.inicio_slot, item.auditor_responsable, item.obra_id))
        metrics = calculate_plan_travel_metrics(result.plan, self.travel_matrix)
        result.auditor_travel_km = metrics.auditor_km
        result.auditor_travel_min = metrics.auditor_min
        result.supervisor_travel_km = metrics.supervisor_km
        result.supervisor_travel_min = metrics.supervisor_min
        result.contractor_travel_km = metrics.contratista_km
        result.contractor_travel_min = metrics.contratista_min

        vehicle = calculate_vehicle_plan(result.plan, self.travel_matrix, self.config)
        result.vehicle_km = vehicle.vehicle_km
        result.vehicle_travel_min = vehicle.vehicle_travel_min
        result.vehicle_trips = vehicle.vehicle_trips
        result.vehicles_required_peak = vehicle.vehicles_required_peak
        result.solo_vehicle_legs = vehicle.solo_legs
        result.shared_vehicle_legs = vehicle.shared_legs
        result.vehicle_plan = list(vehicle.legs)

        quality = calculate_quality_metrics(result.plan, self.travel_matrix, self.config)
        result.waiting_auditor_min = quality.espera_auditor_min
        result.day_imbalance_min = quality.desbalance_dia_min
        result.auditor_imbalance_min = quality.desbalance_auditor_min
        result.companion_changes = quality.cambios_acompanante
        result.operational_cost = quality.costo_operativo
        return result
