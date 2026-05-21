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


def test_run_man_requires_arguments(capsys) -> None:
    exit_code = cli.run_man([])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "must provide arguments" in captured.err
