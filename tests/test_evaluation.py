import pytest
from src.evaluation import validate_verdict, criterion_total

def test_denominator_includes_every_planned_case():
    assert criterion_total([{"criteria":["a","b"]},{"criteria":["c"]}])==3

@pytest.mark.parametrize("rows",[[],[{"criterion":"a","verdict":"PASS"}],[{"criterion":"a","verdict":"PASS"},{"criterion":"a","verdict":"PASS"}],[{"criterion":"a","verdict":"MAYBE"},{"criterion":"b","verdict":"PASS"}]])
def test_incomplete_duplicate_or_invalid_judgments_fail(rows):
    with pytest.raises(ValueError):validate_verdict({"results":rows},["a","b"])

def test_complete_judgment_can_reorder_criteria():
    verdict={"results":[{"criterion":"b","verdict":"FAIL"},{"criterion":"a","verdict":"PASS"}]}
    assert validate_verdict(verdict,["a","b"])==verdict
