import json
import math
from pathlib import Path

import pytest

from relecteur.judges import albert_probability
from relecteur.scorer import JudgeUnavailable

RESPONSES = Path(__file__).parent / "fixtures" / "judges"


def recorded(file):
    return json.loads((RESPONSES / file).read_text())


def test_albert_confirms_a_remark_describing_the_expected_defect():
    assert albert_probability(recorded("albert-same-defect.json")) > 0.99


def test_albert_rejects_a_remark_describing_another_defect():
    assert albert_probability(recorded("albert-other-defect.json")) < 0.01


def first_token(*candidates):
    top_logprobs = [{"token": token, "logprob": math.log(p)} for token, p in candidates]
    return {"choices": [{"logprobs": {"content": [{"top_logprobs": top_logprobs}]}}]}


def test_every_spelling_of_yes_counts_against_every_spelling_of_no():
    answer = first_token(("yes", 0.5), ("Yes", 0.25), (" no", 0.125), ("The", 0.125))

    assert albert_probability(answer) == pytest.approx(0.857, abs=1e-3)


def test_an_answer_that_is_neither_yes_nor_no_is_no_judgment():
    with pytest.raises(JudgeUnavailable):
        albert_probability(first_token(("The", 0.9), ("A", 0.1)))
