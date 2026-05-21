# heyman-cli

`heyman-cli` is a tiny Python command-line wrapper around `man` that disables pager/editor behavior and streams the man page directly to standard output.

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
