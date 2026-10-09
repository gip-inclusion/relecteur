from pathlib import Path

import pytest

from relecteur.cases import (
    Case,
    ExpectedDefect,
    ForbiddenRemark,
    InvalidCases,
    Location,
    load_cases,
)

CASES = Path(__file__).parent / "fixtures" / "cases"


def test_a_pull_request_approved_without_comment_is_loaded_from_its_file():
    cases = load_cases(CASES / "suite" / "approved-without-comment.toml")

    assert cases == [
        Case(
            name="approved-without-comment",
            pull_request="https://forge.example/team/app/pull/1",
            notes="Approved by the maintainer without a single comment: "
            "the reviewer should stay silent.",
            base="b2f7f9a327f098f6ef64d91d13c193353d92ab5d",
            head="38ed0cb00af75b0fd9b533521af64be6dd397be0",
            max_findings=0,
            forbidden_remarks=(
                ForbiddenRemark(
                    path="src/billing.py",
                    line=42,
                    concept="Asks to rename the method although its name matches the domain.",
                ),
            ),
        )
    ]


def test_a_pull_request_fixed_after_its_approval_is_loaded_with_its_expected_defect():
    [case] = load_cases(CASES / "suite" / "fixed-after-approval.toml")

    assert case.expected_defects == (
        ExpectedDefect(
            path="src/billing.py",
            lines=(42,),
            concept="Applies the discount a second time when the invoice total is recomputed.",
            fix="https://forge.example/team/app/pull/4",
            escaped_review=True,
        ),
    )


def test_a_defect_spread_over_several_lines_is_loaded_with_each_of_them():
    [case] = load_cases(CASES / "suite" / "defect-over-two-lines.toml")

    assert case.expected_defects[0].lines == (28, 35)


def test_a_defect_that_also_shows_in_another_file_is_loaded_with_that_location():
    [case] = load_cases(CASES / "suite" / "defect-over-two-lines.toml")

    assert case.expected_defects[0].also_at == (Location(path="src/jobs.py", lines=(12,)),)


def test_the_text_of_a_pull_request_is_its_title_then_its_description():
    [case] = load_cases(CASES / "suite" / "thumbs-up-without-remark.toml")

    assert case.pr.text == (
        "Show the invoice total before taxes\n\n"
        "The accountants asked to see it next to the total with taxes."
    )


def test_a_directory_holds_one_case_per_file():
    cases = load_cases(CASES / "suite")

    assert [case.name for case in cases] == [
        "approved-without-comment",
        "defect-over-two-lines",
        "fixed-after-approval",
        "thumbs-up-without-remark",
    ]


@pytest.mark.parametrize(
    ("file", "problem"),
    [
        ("missing-head.toml", "missing field 'head'"),
        ("abbreviated-sha.toml", "'base' must be a full commit SHA, got 'b2f7f9a'"),
        ("misspelled-field.toml", "unknown field 'max_finding'"),
        ("negative-ceiling.toml", "'max_findings' must be a non-negative integer, got -1"),
        ("not-toml.toml", "not valid TOML: "),
        ("pr-without-title.toml", "pr: missing field 'title'"),
        (
            "other-location-without-path.toml",
            "expected defect 1: other location 1: missing field 'path'",
        ),
        ("remark-without-concept.toml", "forbidden remark 1: missing field 'concept'"),
        (
            "escaped-review-in-words.toml",
            "expected defect 1: 'escaped_review' must be true or false, got 'yes'",
        ),
        (
            "defect-without-lines.toml",
            "expected defect 1: 'line' must be a line number or a non-empty list of line "
            "numbers, got []",
        ),
        (
            "ceiling-below-defects.toml",
            "'max_findings' must allow the 1 expected defect(s), got 0",
        ),
    ],
)
def test_an_invalid_case_is_refused_with_its_file_and_problem(file, problem):
    path = CASES / "invalid" / file

    with pytest.raises(InvalidCases) as error:
        load_cases(path)

    assert f"{path}: {problem}" in str(error.value)


def test_every_invalid_case_of_a_directory_is_reported_at_once():
    directory = CASES / "invalid"

    with pytest.raises(InvalidCases) as error:
        load_cases(directory)

    assert {problem.split(": ")[0] for problem in error.value.problems} == {
        str(file) for file in directory.glob("*.toml")
    }


def test_a_directory_without_any_case_file_is_refused(tmp_path):
    with pytest.raises(InvalidCases) as error:
        load_cases(tmp_path)

    assert str(error.value) == f"{tmp_path}: no case file (*.toml) in this directory"
