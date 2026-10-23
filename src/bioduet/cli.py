import argparse
import json
from .runner import run

def main():
    parser = argparse.ArgumentParser(description="BioDuet synthetic engineering replay; no scientific score")
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo")
    demo.add_argument("--condition", choices=["H0", "H1"], default="H1")
    demo.add_argument("--output", required=True)
    demo.add_argument("--wall-seconds", type=float, default=30)
    args = parser.parse_args()
    report = run(args.output, condition=args.condition, wall_seconds=args.wall_seconds)
    print(json.dumps({k: report[k] for k in ("terminal", "failure", "formal_benchmark_score")}))
    return 0 if report["terminal"] == "participants_finished" and report["failure"] is None else 1

if __name__ == "__main__":
    raise SystemExit(main())
