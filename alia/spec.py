"""Compare measured metrics against a target specification."""


def evaluate(measured: dict, spec: dict):
    """spec: {metric: (op, target)} where op in {">=","<=","~"} (~ = within 5%)."""
    results, ok = {}, True
    for metric, (op, target) in spec.items():
        val = measured.get(metric)
        if val is None:
            results[metric] = ("MISSING", None, target)
            ok = False
            continue
        if op == ">=":
            passed = val >= target
        elif op == "<=":
            passed = val <= target
        elif op == "~":
            passed = abs(val - target) <= 0.05 * abs(target)
        else:
            raise ValueError(f"bad op {op}")
        results[metric] = ("PASS" if passed else "FAIL", val, target)
        ok = ok and passed
    return ok, results
