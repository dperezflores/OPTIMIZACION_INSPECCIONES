from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from src.config import OptimizationConfig
from src.data_loader import load_auditores, load_config, load_obras
from src.models import Auditor, Obra
from src.optimizer import OptimizationRun, find_minimum_feasible_days
from src.validator import validate_dataset


@dataclass(frozen=True)
class OptimizationRequest:
    min_days: int
    max_days: int
    time_limit_seconds: float


@dataclass
class OptimizationContext:
    obras: list[Obra]
    auditores: list[Auditor]
    config: OptimizationConfig
    warnings: list[str]

    @property
    def obras_count(self) -> int:
        return len(self.obras)

    @property
    def auditores_disponibles(self) -> int:
        return sum(a.disponible for a in self.auditores)

    @property
    def total_inspection_hours(self) -> float:
        return sum(o.duracion_minutos for o in self.obras) / 60


DEFAULT_OBRAS_PATH = Path("data/input/obras.csv")
DEFAULT_AUDITORES_PATH = Path("data/input/auditores.csv")
DEFAULT_PARAMS_PATH = Path("data/input/parametros.json")


def load_context(
    obras_path: str | Path = DEFAULT_OBRAS_PATH,
    auditores_path: str | Path = DEFAULT_AUDITORES_PATH,
    params_path: str | Path = DEFAULT_PARAMS_PATH,
) -> OptimizationContext:
    config = load_config(params_path)
    obras = load_obras(obras_path)
    auditores = load_auditores(auditores_path)
    warnings = validate_dataset(obras, auditores, config)
    return OptimizationContext(
        obras=obras,
        auditores=auditores,
        config=config,
        warnings=warnings,
    )


def run_optimization(
    context: OptimizationContext,
    request: OptimizationRequest,
) -> OptimizationRun:
    if request.min_days < 1:
        raise ValueError("El mínimo de días debe ser al menos 1.")
    if request.max_days < request.min_days:
        raise ValueError("El máximo de días no puede ser menor al mínimo.")
    if request.time_limit_seconds <= 0:
        raise ValueError("El tiempo límite debe ser mayor que cero.")

    config = replace(
        context.config,
        time_limit_seconds=request.time_limit_seconds,
    )

    return find_minimum_feasible_days(
        context.obras,
        context.auditores,
        config,
        min_days=request.min_days,
        max_days=request.max_days,
    )
