from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from typing import Sequence

REMOVED_METADATA_SECTIONS = {"AUTHOR", "REPORTING BUGS", "COPYRIGHT"}
SEE_ALSO_HEADING = "SEE ALSO"
FULL_DOCUMENTATION_PREFIX = "Full documentation"


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


def is_section_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped != line:
        return False
    return all(character.isupper() or character in {" ", "-", "&", "/"} for character in stripped)


def split_sections(text: str) -> list[tuple[str | None, list[str]]]:
    sections: list[tuple[str | None, list[str]]] = []
    current_heading: str | None = None
    current_body: list[str] = []

    for line in text.splitlines():
        if is_section_heading(line):
            if current_heading is not None or current_body:
                sections.append((current_heading, current_body))
            current_heading = line.strip()
            current_body = []
        else:
            current_body.append(line)

    if current_heading is not None or current_body:
        sections.append((current_heading, current_body))
    return sections


def filter_metadata_sections(text: str) -> str:
    filtered_blocks: list[str] = []

    for heading, body in split_sections(text):
        if heading in REMOVED_METADATA_SECTIONS:
            continue

        if heading == SEE_ALSO_HEADING:
            body = [line for line in body if line.strip().startswith(FULL_DOCUMENTATION_PREFIX)]
            if not body:
                continue

        if heading is None:
            block = "\n".join(body).strip("\n")
        else:
            body_text = "\n".join(body).rstrip()
            block = heading if not body_text else f"{heading}\n{body_text}"

        if block:
            filtered_blocks.append(block)

    result = "\n\n".join(filtered_blocks)
    if text.endswith("\n") and result:
        result += "\n"
    return result


def post_process_output(output: bytes) -> bytes:
    normalized = normalize_output(output)
    filtered = filter_metadata_sections(normalized.decode("utf-8", errors="replace"))
    return filtered.encode("utf-8")


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

    stdout = post_process_output(completed.stdout)
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
