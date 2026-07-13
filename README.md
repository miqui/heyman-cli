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
