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

OPTION_FLAGS = {
    "--section": "sections",
    "--max-lines": "max_lines",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="heyman",
        description="Run man with paging disabled and print directly to stdout.",
    )
    parser.add_argument(
        "--section",
        dest="sections",
        default=None,
        help="Comma-separated section names to keep, e.g. SYNOPSIS,OPTIONS. May appear before or after the man arguments.",
    )
    parser.add_argument(
        "--max-lines",
        dest="max_lines",
        type=int,
        default=None,
        help="Truncate output to at most this many lines. May appear before or after the man arguments.",
    )
    parser.add_argument(
        "man_args",
        nargs=argparse.REMAINDER,
        help="Arguments passed directly to man, for example: printf or 3 printf",
    )
    return parser


def extract_trailing_options(args: Sequence[str]) -> tuple[list[str], dict[str, str], str | None]:
    """Pull --section/--max-lines out of a token list wherever they appear.

    argparse.REMAINDER swallows every token after the first man argument, so flags
    placed after the man target never reach argparse's own option parsing. This
    recovers them from the remainder instead of forwarding them to `man` verbatim.
    """
    remaining: list[str] = []
    extracted: dict[str, str] = {}
    tokens = list(args)
    i = 0
    while i < len(tokens):
        token = tokens[i]
        matched_flag = next((flag for flag in OPTION_FLAGS if token == flag or token.startswith(flag + "=")), None)
        if matched_flag is None:
            remaining.append(token)
            i += 1
            continue

        key = OPTION_FLAGS[matched_flag]
        if token.startswith(matched_flag + "="):
            extracted[key] = token[len(matched_flag) + 1 :]
            i += 1
        else:
            if i + 1 >= len(tokens):
                return remaining, extracted, f"argument {matched_flag}: expected one argument"
            extracted[key] = tokens[i + 1]
            i += 2
    return remaining, extracted, None


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


def select_sections(text: str, wanted: Sequence[str]) -> str:
    wanted_headings = {name.strip().upper() for name in wanted if name.strip()}
    if not wanted_headings:
        return text

    filtered_blocks: list[str] = []
    for heading, body in split_sections(text):
        if heading is None or heading.upper() not in wanted_headings:
            continue
        body_text = "\n".join(body).rstrip()
        block = heading if not body_text else f"{heading}\n{body_text}"
        filtered_blocks.append(block)

    result = "\n\n".join(filtered_blocks)
    if text.endswith("\n") and result:
        result += "\n"
    return result


def truncate_lines(text: str, max_lines: int | None) -> str:
    if max_lines is None or max_lines <= 0:
        return text

    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text

    truncated = lines[:max_lines]
    truncated.append(f"... [truncated to {max_lines} lines]")
    return "\n".join(truncated) + "\n"


def post_process_output(
    output: bytes,
    *,
    sections: Sequence[str] | None = None,
    max_lines: int | None = None,
) -> bytes:
    normalized = normalize_output(output)
    text = normalized.decode("utf-8", errors="replace")
    if sections:
        text = select_sections(text, sections)
    else:
        text = filter_metadata_sections(text)
    text = truncate_lines(text, max_lines)
    return text.encode("utf-8")


def run_man(
    man_args: Sequence[str],
    *,
    env: dict[str, str] | None = None,
    sections: Sequence[str] | None = None,
    max_lines: int | None = None,
) -> int:
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

    stdout = post_process_output(completed.stdout, sections=sections, max_lines=max_lines)
    if stdout:
        sys.stdout.buffer.write(stdout)
    if completed.stderr:
        sys.stderr.buffer.write(completed.stderr)
    return completed.returncode


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    man_args, trailing, error = extract_trailing_options(args.man_args)
    if error is not None:
        print(f"heyman: error: {error}", file=sys.stderr)
        return 2

    sections_value = trailing.get("sections", args.sections)

    max_lines_raw = trailing.get("max_lines")
    if max_lines_raw is None:
        max_lines_value = args.max_lines
    else:
        try:
            max_lines_value = int(max_lines_raw)
        except ValueError:
            print(f"heyman: error: argument --max-lines: invalid int value: '{max_lines_raw}'", file=sys.stderr)
            return 2

    sections = sections_value.split(",") if sections_value else None
    return run_man(man_args, sections=sections, max_lines=max_lines_value)


if __name__ == "__main__":
    raise SystemExit(main())
