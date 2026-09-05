from __future__ import annotations

import argparse
from dataclasses import replace

from src.data_loader import load_auditores, load_config, load_obras
from src.optimizer import find_minimum_feasible_days
from src.reporting import print_run_summary, save_run
from src.validator import validate_dataset


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Modelo V0 para determinar el mínimo de días factible "
            "para inspecciones físicas."
        )
    )
    parser.add_argument(
        "--data",
        default="data/input/obras.csv",
        help="CSV normalizado de obras.",
    )
    parser.add_argument(
        "--auditors",
        default="data/input/auditores.csv",
        help="CSV de auditores.",
    )
    parser.add_argument(
        "--params",
        default="data/input/parametros.json",
        help="JSON de parámetros.",
    )
    parser.add_argument("--min-days", type=int, default=None)
    parser.add_argument("--max-days", type=int, default=None)
    parser.add_argument(
        "--time-limit",
        type=float,
        default=None,
        help="Segundos máximos de CP-SAT por escenario.",
    )
    parser.add_argument(
        "--output-dir",
        default="data/output",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config = load_config(args.params)

    if args.time_limit is not None:
        config = replace(
            config,
            time_limit_seconds=args.time_limit,
        )

    obras = load_obras(args.data)
    auditores = load_auditores(args.auditors)

    warnings = validate_dataset(obras, auditores, config)
    for warning in warnings:
        print(f"ADVERTENCIA: {warning}")

    run = find_minimum_feasible_days(
        obras,
        auditores,
        config,
        min_days=args.min_days,
        max_days=args.max_days,
    )

    print_run_summary(
        run=run,
        config=config,
        obras_count=len(obras),
        auditores_count=sum(a.disponible for a in auditores),
        total_inspection_hours=sum(
            o.duracion_minutos for o in obras
        )
        / 60,
    )
    save_run(run, config, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
