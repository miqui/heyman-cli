from __future__ import annotations

import argparse
import math
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from typing import Sequence

REMOVED_METADATA_SECTIONS = {"AUTHOR", "REPORTING BUGS", "COPYRIGHT"}
SEE_ALSO_HEADING = "SEE ALSO"
FULL_DOCUMENTATION_PREFIX = "Full documentation"

OPTION_FLAGS = {
    "--section": "sections",
    "--max-lines": "max_lines",
    "--query": "query",
    "--top": "top",
}

DEFAULT_TOP_CHUNKS = 5
FALLBACK_SECTIONS = ("NAME", "SYNOPSIS")

QUERY_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does",
    "for", "from", "how", "i", "in", "is", "it", "my", "of", "on", "or",
    "she", "that", "the", "then", "this", "to", "use", "using", "want",
    "we", "what", "when", "which", "with", "you",
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
        "--query",
        dest="query",
        default=None,
        help="Free-text task context, e.g. 'upload a file with authentication'. Only the man-page chunks most relevant to it are printed.",
    )
    parser.add_argument(
        "--top",
        dest="top",
        type=int,
        default=None,
        help=f"With --query, number of best-matching chunks to keep (default {DEFAULT_TOP_CHUNKS}).",
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


def tokenize(text: str) -> list[str]:
    """Lowercase tokens; option flags like -o/--upload-file survive intact."""
    text = text.lower().replace("‐", "-")
    # Rejoin words that groff hyphenated across a line wrap ("authen-\ntication").
    text = re.sub(r"(?<=[a-z0-9])-\n\s*(?=[a-z0-9])", "", text)
    tokens: list[str] = []
    for raw in text.split():
        stripped = raw.strip(".,;:!?()[]{}<>\"'`=")
        if not stripped:
            continue
        if stripped.startswith("-") and len(stripped) > 1:
            tokens.append(stripped)
            if stripped.startswith("--"):
                tokens.extend(re.findall(r"[a-z0-9]+", stripped))
        else:
            tokens.extend(re.findall(r"[a-z0-9]+", stripped))
    return tokens


def query_terms(query: str) -> list[str]:
    seen: dict[str, None] = {}
    for token in tokenize(query):
        if token.startswith("-") or token not in QUERY_STOPWORDS:
            seen.setdefault(token, None)
    return list(seen)


def starts_option_entry(paragraph: list[str]) -> bool:
    return bool(paragraph) and paragraph[0].lstrip().startswith(("-", "‐"))


def signature_tokens(line: str) -> set[str]:
    """Tokens naming the option a signature line defines: the flags themselves
    plus the words inside long flags (--upload-file -> upload, file). Argument
    placeholders like <file> are excluded so they don't inflate relevance."""
    tokens: set[str] = set()
    for token in tokenize(line):
        if token.startswith("-"):
            tokens.add(token)
            tokens.update(re.findall(r"[a-z0-9]+", token))
    return tokens


def split_chunks(body: list[str]) -> list[list[str]]:
    """Split a section body into chunks.

    Paragraphs are the base unit. A paragraph whose first line is an option
    signature (e.g. '-u, --user <user:password>') opens an option entry, and
    following paragraphs (description, examples, see-also) merge into that
    entry until the next signature — so each option is one self-contained
    chunk.
    """
    paragraphs: list[list[str]] = []
    current: list[str] = []
    for line in body:
        if line.strip():
            current.append(line)
        elif current:
            paragraphs.append(current)
            current = []
    if current:
        paragraphs.append(current)

    merged: list[list[str]] = []
    in_option_entry = False
    for paragraph in paragraphs:
        if starts_option_entry(paragraph):
            merged.append(paragraph)
            in_option_entry = True
        elif in_option_entry:
            merged[-1] = merged[-1] + [""] + paragraph
        else:
            merged.append(paragraph)
    return merged


def score_chunk(
    terms: Sequence[str],
    heading: str | None,
    counts: Counter[str],
    weights: dict[str, float] | None = None,
    signature_tokens: set[str] | None = None,
) -> float:
    heading_tokens = set(tokenize(heading or ""))
    weights = weights or {}
    signature_tokens = signature_tokens or set()
    score = 0.0
    for term in terms:
        weight = weights.get(term, 1.0)
        present = term in counts
        if term.startswith("-"):
            if present:
                score += 4.0
            if term in signature_tokens:
                score += 4.0
            continue
        if term in signature_tokens:
            # The chunk *defines* an option named after this term; rank it
            # above chunks that merely mention the option.
            score += weight
        if present:
            score += weight
        elif len(term) >= 4:
            prefix_hit = any(
                not token.startswith("-") and len(token) >= 4
                and (token.startswith(term) or term.startswith(token))
                for token in counts
            )
            if prefix_hit:
                score += 0.5 * weight
        if term in heading_tokens:
            score += 0.5
    return score


def idf_weights(terms: Sequence[str], chunk_counts: Sequence[Counter[str]]) -> dict[str, float]:
    """Weight rare query terms above ones that appear all over the page."""
    total = len(chunk_counts)
    weights: dict[str, float] = {}
    for term in terms:
        document_frequency = sum(1 for counts in chunk_counts if term in counts)
        weights[term] = 1.0 + math.log((total + 1) / (document_frequency + 1))
    return weights


def select_relevant(text: str, query: str, top: int | None = None) -> str:
    """Keep only the chunks that best match the query, in document order."""
    terms = query_terms(query)
    limit = top if top and top > 0 else DEFAULT_TOP_CHUNKS

    chunks: list[tuple[int, str | None, str, Counter[str], set[str]]] = []
    position = 0
    for heading, body in split_sections(text):
        for chunk in split_chunks(body):
            chunk_text = "\n".join(chunk)
            signature = signature_tokens(chunk[0]) if starts_option_entry(chunk) else set()
            chunks.append((position, heading, chunk_text, Counter(tokenize(chunk_text)), signature))
            position += 1

    weights = idf_weights(terms, [counts for _, _, _, counts, _ in chunks])

    scored: list[tuple[float, int, str | None, str]] = []
    for position, heading, chunk_text, counts, signature in chunks:
        score = score_chunk(terms, heading, counts, weights, signature)
        if score > 0:
            scored.append((score, position, heading, chunk_text))

    if not scored:
        fallback = select_sections(text, FALLBACK_SECTIONS)
        note = f"[heyman] no content matched query {query!r}; showing NAME and SYNOPSIS\n"
        return note + fallback if fallback else note

    best = sorted(scored, key=lambda item: (-item[0], item[1]))[:limit]
    best.sort(key=lambda item: item[1])

    blocks: list[str] = []
    last_heading: object = object()
    for _score, _position, heading, chunk_text in best:
        if heading is not None and heading != last_heading:
            blocks.append(f"{heading}\n{chunk_text}")
        else:
            blocks.append(chunk_text)
        last_heading = heading

    result = "\n\n".join(blocks)
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
    query: str | None = None,
    top: int | None = None,
) -> bytes:
    normalized = normalize_output(output)
    text = normalized.decode("utf-8", errors="replace")
    if sections:
        text = select_sections(text, sections)
    else:
        text = filter_metadata_sections(text)
    if query:
        text = select_relevant(text, query, top)
    text = truncate_lines(text, max_lines)
    return text.encode("utf-8")


def run_man(
    man_args: Sequence[str],
    *,
    env: dict[str, str] | None = None,
    sections: Sequence[str] | None = None,
    max_lines: int | None = None,
    query: str | None = None,
    top: int | None = None,
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

    stdout = post_process_output(completed.stdout, sections=sections, max_lines=max_lines, query=query, top=top)
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
    query_value = trailing.get("query", args.query)

    def resolve_int(key: str, flag: str, parsed_value: int | None) -> tuple[int | None, bool]:
        raw = trailing.get(key)
        if raw is None:
            return parsed_value, True
        try:
            return int(raw), True
        except ValueError:
            print(f"heyman: error: argument {flag}: invalid int value: '{raw}'", file=sys.stderr)
            return None, False

    max_lines_value, ok = resolve_int("max_lines", "--max-lines", args.max_lines)
    if not ok:
        return 2
    top_value, ok = resolve_int("top", "--top", args.top)
    if not ok:
        return 2

    sections = sections_value.split(",") if sections_value else None
    return run_man(man_args, sections=sections, max_lines=max_lines_value, query=query_value, top=top_value)


if __name__ == "__main__":
    raise SystemExit(main())
