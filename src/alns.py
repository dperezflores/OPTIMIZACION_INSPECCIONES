from __future__ import annotations

from dataclasses import dataclass, field
import math
import random
from typing import Callable

from .config import OptimizationConfig
from .distance_matrix import TravelValue
from .feasibility import FeasibilitySolver
from .models import Auditor, Obra, ScenarioResult


@dataclass
class OperatorStats:
    name: str
    weight: float = 1.0
    uses: int = 0
    accepted: int = 0
    improved: int = 0
    best_hits: int = 0


@dataclass
class ALNSResult:
    initial: ScenarioResult
    best: ScenarioResult
    iterations: int
    accepted_moves: int
    improving_moves: int
    history: list[float] = field(default_factory=list)
    operator_stats: list[OperatorStats] = field(default_factory=list)


class ALNSOptimizer:
    """Adaptive Large Neighborhood Search con reparación CP-SAT.

    La destrucción libera subconjuntos de obras. El resto conserva el día actual.
    CP-SAT repara la solución completa respetando todas las restricciones duras.
    Los operadores ajustan su peso según aceptación y mejora obtenida.
    """

    def __init__(
        self,
        obras: list[Obra],
        auditores: list[Auditor],
        config: OptimizationConfig,
        travel_matrix: dict[tuple[str, str], TravelValue],
        *,
        seed: int = 42,
    ) -> None:
        self.obras = obras
        self.auditores = auditores
        self.config = config
        self.travel_matrix = travel_matrix
        self.rng = random.Random(seed)
        self.obra_by_id = {o.obra_id: o for o in obras}
        self.stats = {
            "aleatorio": OperatorStats("Aleatorio"),
            "dia_completo": OperatorStats("Día completo"),
            "geografico": OperatorStats("Geográfico"),
        }

    def _choose_operator(self) -> str:
        names = list(self.stats)
        weights = [max(0.05, self.stats[name].weight) for name in names]
        return self.rng.choices(names, weights=weights, k=1)[0]

    def _destroy_random(self, current: ScenarioResult, fraction: float) -> set[str]:
        count = max(2, min(len(current.plan), round(len(current.plan) * fraction)))
        return set(self.rng.sample([p.obra_id for p in current.plan], count))

    def _destroy_day(self, current: ScenarioResult, fraction: float) -> set[str]:
        days = sorted({p.dia for p in current.plan})
        chosen = self.rng.choice(days)
        ids = [p.obra_id for p in current.plan if p.dia == chosen]
        if len(ids) >= 2:
            return set(ids)
        return self._destroy_random(current, fraction)

    def _destroy_geographic(self, current: ScenarioResult, fraction: float) -> set[str]:
        candidates = [p for p in current.plan if self.obra_by_id[p.obra_id].latitud is not None]
        if not candidates:
            return self._destroy_random(current, fraction)
        seed_item = self.rng.choice(candidates)
        origin = seed_item.obra_id
        scored = []
        for item in current.plan:
            value = self.travel_matrix.get((origin, item.obra_id))
            distance = value.distancia_estimada_km if value else float("inf")
            scored.append((distance, item.obra_id))
        scored.sort(key=lambda x: x[0])
        count = max(2, min(len(scored), round(len(scored) * fraction)))
        return {obra_id for _, obra_id in scored[:count]}

    def _destroy(self, operator: str, current: ScenarioResult, fraction: float) -> set[str]:
        if operator == "dia_completo":
            return self._destroy_day(current, fraction)
        if operator == "geografico":
            return self._destroy_geographic(current, fraction)
        return self._destroy_random(current, fraction)

    @staticmethod
    def _fixed_days(current: ScenarioResult, destroyed: set[str]) -> dict[str, int]:
        return {p.obra_id: p.dia for p in current.plan if p.obra_id not in destroyed}

    def _update_weight(self, operator: str, reward: float, reaction: float = 0.25) -> None:
        stats = self.stats[operator]
        stats.weight = (1.0 - reaction) * stats.weight + reaction * reward

    def optimize(
        self,
        initial: ScenarioResult,
        *,
        iterations: int = 30,
        destroy_fraction: float = 0.20,
        repair_time_limit_seconds: float = 4.0,
        initial_temperature: float = 80.0,
        cooling: float = 0.94,
    ) -> ALNSResult:
        if not initial.factible:
            raise ValueError("ALNS requiere una solución inicial factible.")
        if iterations < 1:
            return ALNSResult(initial, initial, 0, 0, 0, [initial.operational_cost], list(self.stats.values()))

        current = initial
        best = initial
        accepted = 0
        improving = 0
        temperature = max(1e-6, initial_temperature)
        history = [best.operational_cost]

        repair_cfg = self.config.__class__(**{
            **self.config.__dict__,
            "time_limit_seconds": repair_time_limit_seconds,
        })
        solver = FeasibilitySolver(
            self.obras,
            self.auditores,
            repair_cfg,
            travel_matrix=self.travel_matrix,
        )

        for iteration in range(iterations):
            operator = self._choose_operator()
            stats = self.stats[operator]
            stats.uses += 1
            destroyed = self._destroy(operator, current, destroy_fraction)
            fixed_days = self._fixed_days(current, destroyed)
            candidate = solver.solve(
                current.dias,
                fixed_days=fixed_days,
                random_seed=1000 + iteration,
            )
            if not candidate.factible:
                self._update_weight(operator, 0.2)
                temperature *= cooling
                history.append(best.operational_cost)
                continue

            delta = candidate.operational_cost - current.operational_cost
            accept = delta <= 0
            if not accept:
                probability = math.exp(-delta / max(temperature, 1e-6))
                accept = self.rng.random() < probability

            reward = 0.5
            if accept:
                current = candidate
                accepted += 1
                stats.accepted += 1
                reward = 1.5
                if delta < 0:
                    improving += 1
                    stats.improved += 1
                    reward = 3.0
                if candidate.operational_cost < best.operational_cost:
                    best = candidate
                    stats.best_hits += 1
                    reward = 6.0

            self._update_weight(operator, reward)
            temperature *= cooling
            history.append(best.operational_cost)

        return ALNSResult(
            initial=initial,
            best=best,
            iterations=iterations,
            accepted_moves=accepted,
            improving_moves=improving,
            history=history,
            operator_stats=list(self.stats.values()),
        )
