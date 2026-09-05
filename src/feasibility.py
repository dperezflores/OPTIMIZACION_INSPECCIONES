from __future__ import annotations

from collections import defaultdict
from typing import Optional

from ortools.sat.python import cp_model

from .config import OptimizationConfig
from .distance_matrix import TravelValue, build_travel_matrix, calculate_plan_travel_metrics, travel_slots
from .models import Auditor, Obra, PlanItem, ScenarioResult


class FeasibilitySolver:
    """Modelo CP-SAT con matriz de traslado intercambiable.

    Si no se proporciona una matriz externa, mantiene el comportamiento V1 y
    construye la aproximación Haversine. V2 inyecta una matriz de Google Routes.
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
        """Exige duración de actividad + viaje entre usos consecutivos de un recurso."""
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

    def solve(self, dias: int) -> ScenarioResult:
        model = cp_model.CpModel()
        horizon = self.config.slots_por_dia
        days = range(dias)

        assign: dict[tuple[str, int], cp_model.IntVar] = {}
        start: dict[tuple[str, int], cp_model.IntVar] = {}
        companion: dict[tuple[str, int, str], cp_model.IntVar] = {}
        supervisor_choice: dict[tuple[str, int, str], cp_model.IntVar] = {}

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
                            objective_terms.append(3 * z)
                    model.add(sum(z_vars) == y)

                objective_terms.append((d * obra.prioridad * 10) * y)
                objective_terms.append(s)

            model.add_exactly_one(day_vars)

        self._add_resource_travel_constraints(model, auditor_items)
        self._add_resource_travel_constraints(model, contractor_items)
        self._add_resource_travel_constraints(model, supervisor_items)

        model.minimize(sum(objective_terms))

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.config.time_limit_seconds
        solver.parameters.num_search_workers = self.config.num_search_workers
        solver.parameters.random_seed = 42

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

        result.plan = sorted(
            plan,
            key=lambda item: (item.dia, item.inicio_slot, item.auditor_responsable, item.obra_id),
        )
        metrics = calculate_plan_travel_metrics(result.plan, self.travel_matrix)
        result.auditor_travel_km = metrics.auditor_km
        result.auditor_travel_min = metrics.auditor_min
        result.supervisor_travel_km = metrics.supervisor_km
        result.supervisor_travel_min = metrics.supervisor_min
        result.contractor_travel_km = metrics.contratista_km
        result.contractor_travel_min = metrics.contratista_min
        return result
