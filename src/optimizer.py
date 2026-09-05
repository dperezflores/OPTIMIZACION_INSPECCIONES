from __future__ import annotations

from dataclasses import dataclass, field

from .config import OptimizationConfig
from .feasibility import FeasibilitySolver
from .models import Auditor, Obra, ScenarioResult
from .validator import theoretical_lower_bound_days


@dataclass
class OptimizationRun:
    theoretical_lower_bound: int
    scenarios: list[ScenarioResult] = field(default_factory=list)
    best: ScenarioResult | None = None
    minimum_certified: bool = False


def find_minimum_feasible_days(
    obras: list[Obra],
    auditores: list[Auditor],
    config: OptimizationConfig,
    min_days: int | None = None,
    max_days: int | None = None,
) -> OptimizationRun:
    lower_bound = theoretical_lower_bound_days(
        obras,
        auditores,
        config,
    )
    requested_min = min_days if min_days is not None else config.dias_min
    requested_max = max_days if max_days is not None else config.dias_max
    start_days = max(1, requested_min, lower_bound)

    run = OptimizationRun(theoretical_lower_bound=lower_bound)
    solver = FeasibilitySolver(obras, auditores, config)

    earlier_all_proven_infeasible = True
    for dias in range(start_days, requested_max + 1):
        result = solver.solve(dias)
        run.scenarios.append(result)

        if result.factible:
            run.best = result
            run.minimum_certified = earlier_all_proven_infeasible
            break

        if not result.probado_infactible:
            # UNKNOWN o MODEL_INVALID no certifican que el escenario
            # sea imposible.
            earlier_all_proven_infeasible = False

    return run
