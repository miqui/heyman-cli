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


CURL_LIKE_PAGE = """NAME
     curl - transfer a URL

SYNOPSIS
     curl [options / URLs]

OPTIONS
     -d, --data <data>
            (HTTP) Sends the specified data in a POST request to the server.

     -o, --output <file>
            Write output to <file> instead of stdout.

     -T, --upload-file <file>
            This transfers the specified local file to the remote URL.

     -u, --user <user:password>
            Specify the user name and password to use for server
            authentication.

     -v, --verbose
            Makes curl verbose during the operation.
"""


def test_select_relevant_picks_chunks_matching_task_context() -> None:
    result = cli.select_relevant(CURL_LIKE_PAGE, "upload a file with authentication", top=2)

    assert "--upload-file" in result
    assert "--user" in result
    assert "--verbose" not in result
    assert "--data" not in result


def test_select_relevant_boosts_exact_flag_mentions() -> None:
    result = cli.select_relevant(CURL_LIKE_PAGE, "what does -o mean", top=1)

    assert "--output" in result
    assert "--upload-file" not in result


def test_select_relevant_keeps_document_order_and_section_heading() -> None:
    result = cli.select_relevant(CURL_LIKE_PAGE, "upload file user password", top=2)

    assert result.startswith("OPTIONS\n")
    assert result.index("--upload-file") < result.index("--user")
    assert result.count("OPTIONS") == 1


def test_select_relevant_falls_back_to_name_and_synopsis_when_nothing_matches() -> None:
    result = cli.select_relevant(CURL_LIKE_PAGE, "zzzz qqqq", top=3)

    assert result.startswith("[heyman] no content matched query")
    assert "curl - transfer a URL" in result
    assert "curl [options / URLs]" in result
    assert "OPTIONS" not in result


def test_split_chunks_merges_flag_signature_with_description() -> None:
    body = [
        "     -T, --upload-file <file>",
        "",
        "            Transfers the local file to the remote URL.",
        "",
        "     -v, --verbose",
        "            Verbose output.",
    ]

    chunks = cli.split_chunks(body)

    assert len(chunks) == 2
    assert "--upload-file" in chunks[0][0]
    assert any("Transfers the local file" in line for line in chunks[0])


def test_query_terms_drops_stopwords_but_keeps_flags() -> None:
    assert cli.query_terms("I want to use -o for the output") == ["-o", "output"]


def test_post_process_output_applies_query_then_truncation() -> None:
    result = cli.post_process_output(
        CURL_LIKE_PAGE.encode(), query="upload a file", top=1, max_lines=2
    ).decode()

    assert "--upload-file" in result
    assert result.rstrip().endswith("[truncated to 2 lines]")


def test_extract_trailing_options_recovers_query_and_top() -> None:
    remaining, extracted, error = cli.extract_trailing_options(
        ["curl", "--query", "upload a file", "--top", "3"]
    )

    assert remaining == ["curl"]
    assert extracted == {"query": "upload a file", "top": "3"}
    assert error is None


def test_run_man_requires_arguments(capsys) -> None:
    exit_code = cli.run_man([])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "must provide arguments" in captured.err
