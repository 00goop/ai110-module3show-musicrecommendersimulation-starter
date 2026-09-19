"""Deterministic accounting for model-judged criteria, independent of API calls."""
def validate_verdict(verdict, criteria):
    rows = verdict.get("results", []) if isinstance(verdict, dict) else []
    if len(rows) != len(criteria) or sorted(r.get("criterion", "") for r in rows) != sorted(criteria):
        raise ValueError("Judge must return each criterion exactly once")
    if any(r.get("verdict") not in ("PASS", "FAIL") for r in rows):
        raise ValueError("Invalid judge verdict")
    return verdict

def criterion_total(goldens):
    return sum(len(golden["criteria"]) for golden in goldens)
