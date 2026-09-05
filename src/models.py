from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple


TIPO_PROYECTO = "PROYECTO_DOCUMENTAL"
TIPO_FISICA = "INSPECCION_FISICA"


@dataclass(frozen=True)
class Obra:
    """Actividad de revisión: proyecto documental o inspección física."""

    obra_id: str
    contrato: str
    descripcion: str
    auditor_responsable: str
    duracion_minutos: int
    latitud: Optional[float]
    longitud: Optional[float]
    supervisor_preferente_id: Optional[str]
    supervisores_alternativos_ids: Tuple[str, ...] = field(default_factory=tuple)
    contratista_id: Optional[str] = None
    prioridad: int = 3
    tipo_inspeccion: str = ""
    tipo_revision: str = TIPO_FISICA

    @property
    def requiere_acompanante(self) -> bool:
        return self.tipo_revision == TIPO_FISICA

    @property
    def auditores_requeridos(self) -> int:
        return 2 if self.requiere_acompanante else 1

    @property
    def supervisores_candidatos(self) -> Tuple[str, ...]:
        candidatos = []
        if self.supervisor_preferente_id:
            candidatos.append(self.supervisor_preferente_id)
        candidatos.extend(s for s in self.supervisores_alternativos_ids if s and s not in candidatos)
        return tuple(candidatos)


@dataclass(frozen=True)
class Auditor:
    auditor_id: str
    disponible: bool = True
    hora_inicio: str = "08:00"
    hora_fin: str = "17:00"


@dataclass(frozen=True)
class PlanItem:
    obra_id: str
    contrato: str
    descripcion: str
    dia: int
    inicio_slot: int
    fin_slot: int
    auditor_responsable: str
    auditor_acompanante: Optional[str]
    supervisor_seleccionado: Optional[str]
    contratista_id: Optional[str]
    prioridad: int
    tipo_revision: str


@dataclass
class ScenarioResult:
    dias: int
    status: str
    factible: bool
    wall_time_seconds: float
    objective_value: Optional[float] = None
    plan: list[PlanItem] = field(default_factory=list)

    @property
    def probado_infactible(self) -> bool:
        return self.status.upper() == "INFEASIBLE"
