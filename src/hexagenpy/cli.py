"""Entry point of the ``hexapy`` command line.

Phase 0 only exposes ``--version``; the subcommands (new, slice, dev, run,
export, routes, doctor, migrate) arrive in Phase 8.
"""

import argparse
from collections.abc import Sequence

from hexagenpy.__about__ import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hexapy",
        description="hexagenpy CLI: one contract, many transports.",
    )
    parser.add_argument("--version", action="version", version=f"hexagenpy {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    parser.print_help()
    return 0
