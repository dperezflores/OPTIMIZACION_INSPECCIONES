from __future__ import annotations

from collections import defaultdict
from typing import Optional

from ortools.sat.python import cp_model

from .config import OptimizationConfig
from .models import Auditor, Obra, PlanItem, ScenarioResult


class FeasibilitySolver:
    """Modelo CP-SAT V0.1: proyectos solos + acompañante dinámico en campo."""

    def __init__(
        self,
        obras: list[Obra],
        auditores: list[Auditor],
        config: OptimizationConfig,
    ) -> None:
        self.obras = obras
        self.auditores = [a for a in auditores if a.disponible]
        self.config = config
        self.auditor_ids = sorted(a.auditor_id for a in self.auditores)

    def solve(self, dias: int) -> ScenarioResult:
        model = cp_model.CpModel()
        horizon = self.config.slots_por_dia
        days = range(dias)

        assign: dict[tuple[str, int], cp_model.IntVar] = {}
        start: dict[tuple[str, int], cp_model.IntVar] = {}
        companion: dict[tuple[str, int, str], cp_model.IntVar] = {}
        supervisor_choice: dict[tuple[str, int, str], cp_model.IntVar] = {}

        auditor_intervals = defaultdict(list)
        contractor_intervals = defaultdict(list)
        supervisor_intervals = defaultdict(list)
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

                responsable_interval = model.new_optional_fixed_size_interval_var(
                    s,
                    duration,
                    y,
                    f"int_resp__{obra_key}__{obra.auditor_responsable}__d{d}",
                )
                auditor_intervals[(obra.auditor_responsable, d)].append(
                    responsable_interval
                )

                if obra.requiere_acompanante:
                    possible_companions = [
                        a for a in self.auditor_ids
                        if a != obra.auditor_responsable
                    ]
                    companion_vars = []
                    for auditor_id in possible_companions:
                        x = model.new_bool_var(
                            f"comp__{obra_key}__{auditor_id}__d{d}"
                        )
                        companion[(obra_key, d, auditor_id)] = x
                        companion_vars.append(x)

                        comp_interval = model.new_optional_fixed_size_interval_var(
                            s,
                            duration,
                            x,
                            f"int_comp__{obra_key}__{auditor_id}__d{d}",
                        )
                        auditor_intervals[(auditor_id, d)].append(comp_interval)

                    model.add(sum(companion_vars) == y)

                if obra.contratista_id:
                    contractor_interval = model.new_optional_fixed_size_interval_var(
                        s,
                        duration,
                        y,
                        f"int_cont__{obra_key}__{obra.contratista_id}__d{d}",
                    )
                    contractor_intervals[(obra.contratista_id, d)].append(
                        contractor_interval
                    )

                candidates = obra.supervisores_candidatos
                if candidates:
                    z_vars = []
                    for index, supervisor_id in enumerate(candidates):
                        z = model.new_bool_var(
                            f"sup__{obra_key}__{supervisor_id}__d{d}"
                        )
                        supervisor_choice[(obra_key, d, supervisor_id)] = z
                        z_vars.append(z)

                        sup_interval = model.new_optional_fixed_size_interval_var(
                            s,
                            duration,
                            z,
                            f"int_sup__{obra_key}__{supervisor_id}__d{d}",
                        )
                        supervisor_intervals[(supervisor_id, d)].append(sup_interval)

                        if index > 0:
                            objective_terms.append(3 * z)

                    model.add(sum(z_vars) == y)

                objective_terms.append((d * obra.prioridad * 10) * y)
                objective_terms.append(s)

            model.add_exactly_one(day_vars)

        for intervals in auditor_intervals.values():
            if len(intervals) > 1:
                model.add_no_overlap(intervals)
        for intervals in contractor_intervals.values():
            if len(intervals) > 1:
                model.add_no_overlap(intervals)
        for intervals in supervisor_intervals.values():
            if len(intervals) > 1:
                model.add_no_overlap(intervals)

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
            key=lambda item: (
                item.dia,
                item.inicio_slot,
                item.auditor_responsable,
                item.obra_id,
            ),
        )
        return result
