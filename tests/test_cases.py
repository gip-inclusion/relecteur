from pathlib import Path

import pytest

from relecteur.cases import Case, ForbiddenRemark, InvalidCases, load_cases

CASES = Path(__file__).parent / "fixtures" / "cases"


def test_a_pull_request_approved_without_comment_is_loaded_from_its_file():
    cases = load_cases(CASES / "suite" / "approved-without-comment.toml")

    assert cases == [
        Case(
            name="approved-without-comment",
            pull_request="https://forge.example/team/app/pull/1",
            description="Approved by the maintainer without a single comment: "
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


def test_a_directory_holds_one_case_per_file():
    cases = load_cases(CASES / "suite")

    assert [case.name for case in cases] == [
        "approved-without-comment",
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
        ("remark-without-concept.toml", "forbidden remark 1: missing field 'concept'"),
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
