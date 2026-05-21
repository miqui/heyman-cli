from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from typing import Sequence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="heyman",
        description="Run man with paging disabled and print directly to stdout.",
    )
    parser.add_argument(
        "man_args",
        nargs=argparse.REMAINDER,
        help="Arguments passed directly to man, for example: printf or 3 printf",
    )
    return parser


def build_command(man_args: Sequence[str]) -> list[str]:
    return ["man", *man_args]


def build_env(base_env: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(base_env if base_env is not None else os.environ)
    env["PAGER"] = "cat"
    env["MANPAGER"] = "cat"
    env.setdefault("LESS", "-F -X")
    return env


def normalize_output(output: bytes) -> bytes:
    col_path = shutil.which("col")
    if not col_path:
        return output

    cleaned = subprocess.run(
        [col_path, "-bx"],
        input=output,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if cleaned.returncode != 0:
        return output
    return cleaned.stdout


def run_man(man_args: Sequence[str], *, env: dict[str, str] | None = None) -> int:
    if not man_args:
        print("error: you must provide arguments to pass to man", file=sys.stderr)
        return 2

    try:
        completed = subprocess.run(
            build_command(man_args),
            env=build_env(env),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError:
        print("error: 'man' command not found on PATH", file=sys.stderr)
        return 127

    stdout = normalize_output(completed.stdout)
    if stdout:
        sys.stdout.buffer.write(stdout)
    if completed.stderr:
        sys.stderr.buffer.write(completed.stderr)
    return completed.returncode


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run_man(args.man_args)


if __name__ == "__main__":
    raise SystemExit(main())
