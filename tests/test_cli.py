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


def test_select_sections_keeps_only_requested_headings() -> None:
    raw = """NAME
     printf - format and print data

SYNOPSIS
     printf FORMAT [ARGUMENT]...

DESCRIPTION
     Useful text.
"""

    selected = cli.select_sections(raw, ["synopsis"])

    assert selected == "SYNOPSIS\n     printf FORMAT [ARGUMENT]...\n"


def test_select_sections_returns_text_unchanged_when_no_sections_given() -> None:
    raw = "NAME\n     printf - format and print data\n"
    assert cli.select_sections(raw, []) == raw


def test_select_sections_drops_headings_not_present() -> None:
    raw = "NAME\n     printf - format and print data\n"
    assert cli.select_sections(raw, ["OPTIONS"]) == ""


def test_truncate_lines_leaves_short_output_untouched() -> None:
    text = "line one\nline two\n"
    assert cli.truncate_lines(text, 10) == text


def test_truncate_lines_truncates_and_appends_marker() -> None:
    text = "\n".join(f"line {i}" for i in range(5)) + "\n"

    truncated = cli.truncate_lines(text, 2)

    assert truncated == "line 0\nline 1\n... [truncated to 2 lines]\n"


def test_truncate_lines_ignores_non_positive_limits() -> None:
    text = "line one\nline two\n"
    assert cli.truncate_lines(text, None) == text
    assert cli.truncate_lines(text, 0) == text


def test_post_process_output_applies_section_filter_and_truncation() -> None:
    raw = b"""NAME
     printf - format and print data

SYNOPSIS
     printf FORMAT [ARGUMENT]...
     line two
     line three
"""

    result = cli.post_process_output(raw, sections=["SYNOPSIS"], max_lines=2)

    assert result == b"SYNOPSIS\n     printf FORMAT [ARGUMENT]...\n... [truncated to 2 lines]\n"


def test_post_process_output_section_filter_bypasses_metadata_removal() -> None:
    raw = b"""NAME
     ls - list directory contents

AUTHOR
     Written by Someone.
"""

    result = cli.post_process_output(raw, sections=["AUTHOR"])

    assert result == b"AUTHOR\n     Written by Someone.\n"


def test_post_process_output_still_filters_metadata_when_no_sections_requested() -> None:
    raw = b"""NAME
     ls - list directory contents

AUTHOR
     Written by Someone.
"""

    result = cli.post_process_output(raw)

    assert b"AUTHOR" not in result


def test_extract_trailing_options_recovers_flags_after_man_args() -> None:
    remaining, extracted, error = cli.extract_trailing_options(["printf", "--section", "SYNOPSIS"])

    assert remaining == ["printf"]
    assert extracted == {"sections": "SYNOPSIS"}
    assert error is None


def test_extract_trailing_options_supports_equals_form() -> None:
    remaining, extracted, error = cli.extract_trailing_options(["printf", "--max-lines=5"])

    assert remaining == ["printf"]
    assert extracted == {"max_lines": "5"}
    assert error is None


def test_extract_trailing_options_reports_missing_value() -> None:
    remaining, extracted, error = cli.extract_trailing_options(["printf", "--section"])

    assert error == "argument --section: expected one argument"


def test_extract_trailing_options_leaves_unrelated_tokens_untouched() -> None:
    remaining, extracted, error = cli.extract_trailing_options(["3", "printf", "-k"])

    assert remaining == ["3", "printf", "-k"]
    assert extracted == {}
    assert error is None


def test_run_man_requires_arguments(capsys) -> None:
    exit_code = cli.run_man([])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "must provide arguments" in captured.err
