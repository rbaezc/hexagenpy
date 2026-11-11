"""Benchmark runner.

python -m benchmarks.run                       # every installed framework, every scenario
python -m benchmarks.run -f fastapi litestar -s body -n 20000
python -m benchmarks.run --json benchmarks/results/latest.json
"""

import argparse
import asyncio
import gc
import importlib
import json
import platform
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from benchmarks.asgi_client import ASGIApp, Lifespan, call
from benchmarks.scenarios import SCENARIOS, Scenario

FRAMEWORKS = ["hexagenpy", "fastapi", "litestar", "starlette"]


@dataclass(frozen=True)
class Result:
    framework: str
    scenario: str
    iterations: int
    ops_per_sec: float
    p50_us: float
    p99_us: float


def load_app(framework: str) -> ASGIApp | None:
    try:
        module = importlib.import_module(f"benchmarks.apps.{framework}_app")
    except ImportError as exc:
        print(f"  - {framework}: skipped ({exc})", file=sys.stderr)
        return None
    app: ASGIApp | None = getattr(module, "app", None)
    return app


async def measure(app: ASGIApp, framework: str, sc: Scenario, n: int, warmup: int) -> Result:
    status, body = await call(app, sc)
    if status != sc.expected_status:
        raise AssertionError(f"{framework}/{sc.name}: status {status}, body {body[:200]!r}")
    for _ in range(warmup):
        await call(app, sc)
    samples: list[int] = []
    gc.collect()
    gc.disable()
    try:
        start = time.perf_counter_ns()
        for _ in range(n):
            t0 = time.perf_counter_ns()
            await call(app, sc)
            samples.append(time.perf_counter_ns() - t0)
        total = time.perf_counter_ns() - start
    finally:
        gc.enable()
    q = statistics.quantiles(samples, n=100)
    return Result(framework, sc.name, n, n / (total / 1e9), q[49] / 1e3, q[98] / 1e3)


async def run(frameworks: list[str], scenarios: list[str], n: int, warmup: int) -> list[Result]:
    results: list[Result] = []
    for fw in frameworks:
        app = load_app(fw)
        if app is None:
            continue
        async with Lifespan(app):
            results.extend([await measure(app, fw, SCENARIOS[s], n, warmup) for s in scenarios])
    return results


def print_table(results: list[Result]) -> None:
    print(f"\n{'framework':<12}{'scenario':<10}{'ops/s':>12}{'p50 us':>10}{'p99 us':>10}")
    print("-" * 54)
    for r in sorted(results, key=lambda r: (r.scenario, -r.ops_per_sec)):
        print(
            f"{r.framework:<12}{r.scenario:<10}{r.ops_per_sec:>12,.0f}"
            f"{r.p50_us:>10.1f}{r.p99_us:>10.1f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="hexagenpy in-process ASGI benchmarks")
    parser.add_argument("-f", "--frameworks", nargs="+", default=FRAMEWORKS, choices=FRAMEWORKS)
    parser.add_argument(
        "-s", "--scenarios", nargs="+", default=list(SCENARIOS), choices=list(SCENARIOS)
    )
    parser.add_argument("-n", "--iterations", type=int, default=10_000)
    parser.add_argument("-w", "--warmup", type=int, default=1_000)
    parser.add_argument("--json", type=Path, help="write results to this file")
    args = parser.parse_args()

    results = asyncio.run(run(args.frameworks, args.scenarios, args.iterations, args.warmup))
    print_table(results)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "python": sys.version,
            "platform": platform.platform(),
            "results": [asdict(r) for r in results],
        }
        args.json.write_text(json.dumps(payload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
