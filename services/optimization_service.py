from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from services.google_routes_service import (
    GoogleRoutesMatrix,
    build_google_routes_matrix,
    load_cache,
    unique_locations,
)
from src.config import OptimizationConfig
from src.data_loader import load_auditores, load_config, load_obras
from src.models import Auditor, Obra
from src.optimizer import OptimizationRun, find_minimum_feasible_days
from src.validator import validate_dataset


TRAVEL_PROVIDER_GOOGLE = "google_routes"
TRAVEL_PROVIDER_HAVERSINE = "haversine_v1"


@dataclass(frozen=True)
class OptimizationRequest:
    min_days: int
    max_days: int
    time_limit_seconds: float
    travel_provider: str = TRAVEL_PROVIDER_GOOGLE
    google_api_key: str | None = None
    force_refresh_routes: bool = False
    compare_all_scenarios: bool = True


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

    @property
    def unique_location_count(self) -> int:
        return len(unique_locations(self.obras))


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
    return OptimizationContext(obras=obras, auditores=auditores, config=config, warnings=warnings)


def google_cache_status(context: OptimizationContext) -> GoogleRoutesMatrix | None:
    return load_cache(context.obras)


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

    config = replace(context.config, time_limit_seconds=request.time_limit_seconds)

    travel_matrix = None
    travel_source = TRAVEL_PROVIDER_HAVERSINE
    unique_count = context.unique_location_count
    billed_elements = 0

    if request.travel_provider == TRAVEL_PROVIDER_GOOGLE:
        google_matrix = build_google_routes_matrix(
            context.obras,
            request.google_api_key or "",
            force_refresh=request.force_refresh_routes,
        )
        travel_matrix = google_matrix.matrix
        travel_source = google_matrix.source
        unique_count = google_matrix.unique_locations
        billed_elements = google_matrix.billed_elements
    elif request.travel_provider != TRAVEL_PROVIDER_HAVERSINE:
        raise ValueError(f"Proveedor de traslados no reconocido: {request.travel_provider!r}")

    return find_minimum_feasible_days(
        context.obras,
        context.auditores,
        config,
        min_days=request.min_days,
        max_days=request.max_days,
        travel_matrix=travel_matrix,
        travel_source=travel_source,
        unique_locations=unique_count,
        billed_elements=billed_elements,
        evaluate_all=request.compare_all_scenarios,
    )
