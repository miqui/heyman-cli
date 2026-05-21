from __future__ import annotations

from heyman_cli import cli


def test_build_command_preserves_arguments() -> None:
    assert cli.build_command(["3", "printf"]) == ["man", "3", "printf"]


def test_build_env_forces_cat_pagers() -> None:
    env = cli.build_env({"PAGER": "less", "MANPAGER": "most"})
    assert env["PAGER"] == "cat"
    assert env["MANPAGER"] == "cat"
    assert env["LESS"] == "-F -X"


def test_normalize_output_returns_original_when_col_missing(monkeypatch) -> None:
    monkeypatch.setattr(cli.shutil, "which", lambda _: None)
    raw = b"N\bNA\bAM\bME\bE\n"
    assert cli.normalize_output(raw) == raw


def test_filter_metadata_sections_removes_trailing_sections_but_keeps_full_docs() -> None:
    raw = """NAME
     ls - list directory contents

AUTHOR
     Written by Someone.

REPORTING BUGS
     Report bugs somewhere.

COPYRIGHT
     Copyright text.

SEE ALSO
     Full documentation <https://www.gnu.org/software/coreutils/ls>
     or available locally via: info '(coreutils) ls invocation'
"""

    filtered = cli.filter_metadata_sections(raw)

    assert "AUTHOR" not in filtered
    assert "REPORTING BUGS" not in filtered
    assert "COPYRIGHT" not in filtered
    assert "SEE ALSO" in filtered
    assert "Full documentation <https://www.gnu.org/software/coreutils/ls>" in filtered
    assert "or available locally via:" not in filtered


def test_filter_metadata_sections_preserves_non_metadata_sections() -> None:
    raw = """NAME
     printf - format and print data

DESCRIPTION
     Useful text.

EXIT STATUS
     Returns 0 on success.
"""

    assert cli.filter_metadata_sections(raw) == raw


def test_run_man_requires_arguments(capsys) -> None:
    exit_code = cli.run_man([])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "must provide arguments" in captured.err
