from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Optional

from .config import OptimizationConfig
from .models import Auditor, Obra, TIPO_FISICA, TIPO_PROYECTO


NULL_VALUES = {"", "SIN DATO", "N/A", "NA", "NONE", "NULL"}
DGOP_COORD = (21.0992260761766, -101.65788506932189)


def _optional_text(value: object) -> Optional[str]:
    text = "" if value is None else str(value).strip()
    if text.upper() in NULL_VALUES:
        return None
    return text


def _parse_float(value: object) -> Optional[float]:
    text = _optional_text(value)
    if text is None:
        return None
    return float(text.replace(",", "").strip())


def _parse_ids(value: object) -> tuple[str, ...]:
    text = _optional_text(value)
    if text is None:
        return tuple()
    return tuple(item.strip() for item in text.replace("|", ";").split(";") if item.strip())


def _parse_bool(value: object, default: bool = True) -> bool:
    text = _optional_text(value)
    if text is None:
        return default
    return text.strip().upper() in {"1", "TRUE", "SI", "SÍ", "YES", "Y"}


def _tipo_revision(row: dict, latitud: Optional[float], longitud: Optional[float]) -> str:
    explicit = _optional_text(row.get("tipo_revision"))
    if explicit:
        value = explicit.upper().strip()
        if value in {TIPO_PROYECTO, TIPO_FISICA}:
            return value
        raise ValueError(f"tipo_revision no reconocido: {explicit!r}")

    # Migración V0.1: las actividades en la coordenada conocida de la DGOP
    # corresponden actualmente a revisión documental de proyectos.
    if latitud is not None and longitud is not None:
        if abs(latitud - DGOP_COORD[0]) < 1e-9 and abs(longitud - DGOP_COORD[1]) < 1e-9:
            return TIPO_PROYECTO
    return TIPO_FISICA


def load_obras(path: str | Path) -> list[Obra]:
    path = Path(path)
    if path.suffix.lower() != ".csv":
        raise ValueError("La V0 usa CSV para versionar y comparar los datos en GitHub.")

    obras: list[Obra] = []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        required = {"obra_id", "contrato", "obra", "auditor_responsable", "duracion_horas", "supervisor_preferente_id", "supervisores_alternativos_ids", "contratista_id", "prioridad"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Faltan columnas obligatorias en {path}: {sorted(missing)}")

        for row in reader:
            duracion_horas = float(str(row["duracion_horas"]).strip())
            latitud = _parse_float(row.get("latitud"))
            longitud = _parse_float(row.get("longitud"))
            prioridad_text = _optional_text(row.get("prioridad"))
            obras.append(Obra(
                obra_id=str(row["obra_id"]).strip(),
                contrato=str(row.get("contrato", "")).strip(),
                descripcion=str(row.get("obra", "")).strip(),
                auditor_responsable=str(row["auditor_responsable"]).strip(),
                duracion_minutos=int(round(duracion_horas * 60)),
                latitud=latitud,
                longitud=longitud,
                supervisor_preferente_id=_optional_text(row.get("supervisor_preferente_id")),
                supervisores_alternativos_ids=_parse_ids(row.get("supervisores_alternativos_ids")),
                contratista_id=_optional_text(row.get("contratista_id")),
                prioridad=int(prioridad_text or 3),
                tipo_inspeccion=str(row.get("tipo_inspeccion", "")).strip(),
                tipo_revision=_tipo_revision(row, latitud, longitud),
            ))
    return obras


def load_auditores(path: str | Path) -> list[Auditor]:
    path = Path(path)
    auditores: list[Auditor] = []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        required = {"auditor_id"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Faltan columnas obligatorias en {path}: {sorted(missing)}")
        for row in reader:
            auditores.append(Auditor(
                auditor_id=str(row["auditor_id"]).strip(),
                disponible=_parse_bool(row.get("disponible"), True),
                hora_inicio=str(row.get("hora_inicio") or "08:00").strip(),
                hora_fin=str(row.get("hora_fin") or "17:00").strip(),
            ))
    return auditores


def load_config(path: str | Path | None = None) -> OptimizationConfig:
    if path is None:
        return OptimizationConfig()
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    allowed = {"hora_inicio", "hora_fin", "slot_minutos", "dias_min", "dias_max", "time_limit_seconds", "num_search_workers", "prioridad_default", "modo_parejas"}
    return OptimizationConfig(**{key: value for key, value in raw.items() if key in allowed})
