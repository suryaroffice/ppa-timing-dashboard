"""Command line entry point: python -m ppa_parser <files or folders> [-o out.csv]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from .parser import build_dataframe


def collect_files(inputs) -> list:
    files = []
    for item in inputs:
        p = Path(item)
        if p.is_dir():
            files.extend(sorted(p.glob("*.rpt")))
        elif p.is_file():
            files.append(p)
        else:
            print(f"warning: {item} not found, skipping", file=sys.stderr)
    return files


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="ppa_parser",
        description="Parse OpenROAD/OpenSTA-style reports into a PPA table.",
    )
    ap.add_argument("inputs", nargs="+", help="report files or folders of *.rpt")
    ap.add_argument("-o", "--output", help="write the table to this CSV path")
    args = ap.parse_args(argv)

    files = collect_files(args.inputs)
    if not files:
        print("error: no report files found", file=sys.stderr)
        return 1

    df = build_dataframe(files)
    with pd.option_context("display.width", 200, "display.max_columns", None):
        print(df.to_string(index=False))
    if args.output:
        df.to_csv(args.output, index=False)
        print(f"\nwrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
