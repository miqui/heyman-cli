# heyman-cli

`heyman-cli` is a tiny Python command-line wrapper around `man` that disables pager/editor behavior and streams the man page directly to standard output. Great for AI agents that need context!

## Agent SKILL

Can easily be described in a SKILL.MD file without the need for a CLI wrapper ?? TBD

## Why

Commands like `man printf` often invoke `less` or another pager. This project wraps `man` and forces:

- `PAGER=cat`
- `MANPAGER=cat`

That makes it friendlier for scripts, piping, and non-interactive use.

## Usage

```bash
uv run heyman printf
uv run heyman 3 printf
uv run heyman -k printf
```

To keep output small for agent context budgets, filter to specific sections and/or cap the line count. These flags may appear before or after the man arguments:

```bash
uv run heyman --section SYNOPSIS,OPTIONS printf
uv run heyman --max-lines 200 git
uv run heyman curl --section SYNOPSIS --max-lines 20
```

### Context-aware relevance (`--query`)

When an agent knows *what it is trying to do*, pass that context as `--query` and heyman returns only the man-page chunks most relevant to it — typically the handful of option entries that matter — instead of the whole page:

```bash
uv run heyman curl --query "upload a file with authentication"
uv run heyman curl --query "follow redirects and silence progress output" --top 3
uv run heyman tar --query "extract a gzip archive into a specific directory" --max-lines 40
```

- `--top N` controls how many best-matching chunks are kept (default 5); combine with `--max-lines` for a hard cap.
- Chunks are whole option entries (flag signature plus description, examples, and see-also), or paragraphs for prose sections.
- Ranking is lexical and offline (no network, no dependencies): rare query terms weigh more than common ones (IDF), exact flag mentions like `-o` or `--upload-file` in the query are boosted, and the chunk that *defines* an option outranks chunks that merely mention it.
- If nothing matches, heyman falls back to NAME and SYNOPSIS with a note, so the agent always gets something useful.

Equivalent behavior:

```bash
PAGER=cat MANPAGER=cat man printf
```

## Installation

Install it as a local tool with `uv`:

```bash
uv tool install .
heyman printf
```

If you are working from the repo and want to refresh the installed tool after edits:

```bash
uv tool install --reinstall .
```

## Development

Create the environment and run tests:

```bash
uv sync --dev
uv run pytest
```

Run directly from the checkout without installing:

```bash
uv run heyman printf
```

## Notes

- Exit code mirrors the underlying `man` command.
- If `man` is not installed or not on `PATH`, the CLI exits with code `127`.
- If no arguments are provided, the CLI exits with code `2` and prints an error to `stderr`.
- On systems where `col` is available, output is normalized to plain text to strip man-page overstrike formatting.
- `--section` matches heading names case-insensitively; unmatched names are silently dropped (no error).
- `--section` bypasses the default AUTHOR/REPORTING BUGS/COPYRIGHT/SEE-ALSO filtering, so `--section AUTHOR` can select sections that are hidden in the default (unfiltered `--section`) view.
- `--max-lines` truncates *after* section filtering and appends a `... [truncated to N lines]` marker; the marker itself counts as one extra line beyond the limit.
- `--query` runs after section filtering (so `--section OPTIONS --query ...` ranks only within OPTIONS) and before `--max-lines` truncation. Matched chunks are printed in document order under their section headings.
