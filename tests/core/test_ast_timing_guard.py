"""
AST Timing Guard Test Suite.

Scans all test files under tests/ to ensure that NO test in the default suite
contains an unmarked absolute wall-clock timing assertion (e.g. `assert duration < 2.0`).
Timing assertions that benchmark performance MUST be explicitly decorated with `@pytest.mark.perf`.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TESTS_DIR = REPO_ROOT / "tests"


@pytest.fixture(autouse=True)
def ensure_sample_data() -> None:
    """Override conftest db fixture: no database needed for AST inspection."""
    return None


TIMING_VAR_NAMES = {
    "duration",
    "elapsed",
    "elapsed_time",
    "latency",
    "latency_ms",
    "diff_ms",
    "time_taken",
    "duration_ms",
    "response_time",
    "total_time",
    "execution_time",
    "query_time",
    "request_time",
    "process_time",
    "wall_time",
}

DOMAIN_MODEL_NAMES = {
    "session",
    "ticket",
    "booking",
    "contract",
    "vehicle",
    "parking_session",
}


def _is_perf_expr(expr: ast.AST) -> bool:
    """Check if an expression represents a perf marker/decorator."""
    if isinstance(expr, ast.Attribute) and expr.attr == "perf":
        return True
    if isinstance(expr, ast.Name) and expr.id == "perf":
        return True
    if isinstance(expr, ast.Call):
        func = expr.func
        if isinstance(func, ast.Attribute) and func.attr == "perf":
            return True
        if isinstance(func, ast.Name) and func.id == "perf":
            return True
    return False


def _has_perf_marker(node: ast.AST) -> bool:
    """Check if the AST node decorator list contains @pytest.mark.perf or @perf."""
    decorators = getattr(node, "decorator_list", [])
    if isinstance(decorators, list):
        for decorator in decorators:
            if isinstance(decorator, ast.AST) and _is_perf_expr(decorator):
                return True
    return False


def _is_module_perf_marked(tree: ast.Module) -> bool:
    """Detect module-level pytestmark = pytest.mark.perf or pytestmark = [pytest.mark.perf]."""
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "pytestmark":
                    val = node.value
                    if _is_perf_expr(val):
                        return True
                    if isinstance(val, (ast.List, ast.Tuple)):
                        for elt in val.elts:
                            if _is_perf_expr(elt):
                                return True
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "pytestmark"
            and node.value is not None
        ):
            if _is_perf_expr(node.value):
                return True
            if isinstance(node.value, (ast.List, ast.Tuple)):
                for elt in node.value.elts:
                    if _is_perf_expr(elt):
                        return True
    return False


def _is_timing_expression(node: ast.AST) -> bool:
    """Identify if an expression represents a wall-clock timing calculation or variable."""
    if isinstance(node, ast.Name):
        lower = node.id.lower()
        if lower in TIMING_VAR_NAMES or lower.endswith(
            ("_duration", "_latency", "_elapsed", "_time")
        ):
            return True
    elif isinstance(node, ast.Attribute):
        lower = node.attr.lower()
        owner_name = None
        if isinstance(node.value, ast.Name):
            owner_name = node.value.id.lower()
        elif isinstance(node.value, ast.Attribute):
            owner_name = node.value.attr.lower()
        # Avoid false positives on business models with duration attributes
        if owner_name in DOMAIN_MODEL_NAMES:
            return False
        if lower in TIMING_VAR_NAMES or lower.endswith(
            ("_duration", "_latency", "_elapsed", "_time")
        ):
            return True
    elif isinstance(node, ast.Subscript):
        owner_name = None
        if isinstance(node.value, ast.Name):
            owner_name = node.value.id.lower()
        elif isinstance(node.value, ast.Attribute):
            owner_name = node.value.attr.lower()
        if owner_name in DOMAIN_MODEL_NAMES:
            return False
        if isinstance(node.slice, ast.Constant):
            slice_str = str(node.slice.value).lower()
            if slice_str in TIMING_VAR_NAMES or slice_str.endswith(
                ("_duration", "_latency", "_elapsed", "_time")
            ):
                return True
    elif isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in {
            "monotonic",
            "perf_counter",
            "time",
        }:
            return True
        if isinstance(func, ast.Name) and func.id in {
            "monotonic",
            "perf_counter",
            "time",
        }:
            return True
        if (
            isinstance(func, ast.Name)
            and func.id in {"round", "float", "int", "abs"}
            and node.args
        ):
            return _is_timing_expression(node.args[0])
    elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Sub, ast.Add)):
        return _is_timing_expression(node.left) or _is_timing_expression(node.right)
    elif isinstance(node, ast.UnaryOp):
        return _is_timing_expression(node.operand)
    return False


def find_unmarked_wall_clock_assertions_in_source(
    source_code: str, file_path: str = "<memory>"
) -> list[dict[str, str | int]]:
    """Parse AST and detect any unmarked absolute wall-clock assertions."""
    violations: list[dict[str, str | int]] = []
    try:
        tree = ast.parse(source_code, filename=file_path)
    except SyntaxError:
        return violations

    if _is_module_perf_marked(tree):
        return []

    # Map class-level perf markers and all their descendant functions
    perf_functions: set[ast.AST] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ClassDef) and _has_perf_marker(n):
            for sub in ast.walk(n):
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    perf_functions.add(sub)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("test_") and not node.name.endswith("_test"):
                continue

            if _has_perf_marker(node) or node in perf_functions:
                continue

            for inner in ast.walk(node):
                if isinstance(inner, ast.Assert):
                    for comp in ast.walk(inner.test):
                        if isinstance(comp, ast.Compare):
                            operands = [comp.left] + comp.comparators
                            for op, lhs, rhs in zip(
                                comp.ops, operands[:-1], operands[1:], strict=False
                            ):
                                # Case 1: < or <= with timing on left and number on right
                                # Case 2: > or >= with number on left and timing on right (inverted)
                                is_violation = (
                                    isinstance(op, (ast.Lt, ast.LtE))
                                    and _is_timing_expression(lhs)
                                    and isinstance(rhs, ast.Constant)
                                    and isinstance(rhs.value, (int, float))
                                ) or (
                                    isinstance(op, (ast.Gt, ast.GtE))
                                    and _is_timing_expression(rhs)
                                    and isinstance(lhs, ast.Constant)
                                    and isinstance(lhs.value, (int, float))
                                )

                                if is_violation:
                                    violations.append(
                                        {
                                            "file": file_path,
                                            "function": node.name,
                                            "line": inner.lineno,
                                            "expression": ast.unparse(comp),
                                        }
                                    )
                                    break
    return violations


def test_ast_timing_guard_scans_all_tests_clean() -> None:
    """
    Ensure NO test in the default test suite contains unmarked absolute timing assertions.
    All performance-related assertions must be placed behind @pytest.mark.perf.
    Scans both test_*.py and *_test.py files across the entire tests/ directory.
    """
    all_violations: list[dict[str, str | int]] = []
    test_files = sorted(
        set(TESTS_DIR.rglob("test_*.py")) | set(TESTS_DIR.rglob("*_test.py"))
    )

    assert len(test_files) > 0, "No test files discovered under tests/!"

    for test_file in test_files:
        # Skip self test file
        if test_file.name == "test_ast_timing_guard.py":
            continue

        content = test_file.read_text(encoding="utf-8", errors="ignore")
        file_violations = find_unmarked_wall_clock_assertions_in_source(
            content, str(test_file.relative_to(REPO_ROOT))
        )
        all_violations.extend(file_violations)

    assert all_violations == [], (
        "Found unmarked wall-clock timing assertions in default test suite:\n"
        + "\n".join(
            f"  - {v['file']}:{v['line']} in `{v['function']}`: `{v['expression']}`"
            for v in all_violations
        )
    )


def test_ast_timing_guard_synthetic_positive() -> None:
    """Verify that AST Timing Guard detects unmarked assert duration < 2.0 correctly."""
    bad_code = """
def test_dos_attack():
    duration = 1.5
    assert duration < 2.0
"""
    violations = find_unmarked_wall_clock_assertions_in_source(
        bad_code, "test_synthetic.py"
    )
    assert len(violations) == 1
    assert violations[0]["function"] == "test_dos_attack"
    assert violations[0]["line"] == 4
    assert "duration < 2.0" in str(violations[0]["expression"])


def test_ast_timing_guard_synthetic_marked_perf_ignored() -> None:
    """Verify that tests marked with @pytest.mark.perf are exempted from wall-clock assertion guard."""
    marked_code = """
@pytest.mark.perf
def test_perf_latency():
    duration = 1.5
    assert duration < 2.0
"""
    violations = find_unmarked_wall_clock_assertions_in_source(
        marked_code, "test_synthetic.py"
    )
    assert len(violations) == 0


def test_ast_timing_guard_inverted_comparisons() -> None:
    """Verify detection of inverted comparisons (> or >= with constant on lhs, timing on rhs)."""
    code_gt = """
def test_inverted_gt():
    duration = 1.0
    assert 2.0 > duration
"""
    v_gt = find_unmarked_wall_clock_assertions_in_source(code_gt, "test_inv.py")
    assert len(v_gt) == 1
    assert v_gt[0]["function"] == "test_inverted_gt"
    assert "2.0 > duration" in str(v_gt[0]["expression"])

    code_gte = """
def test_inverted_gte():
    latency = 50.0
    assert 100.0 >= latency
"""
    v_gte = find_unmarked_wall_clock_assertions_in_source(code_gte, "test_inv.py")
    assert len(v_gte) == 1
    assert v_gte[0]["function"] == "test_inverted_gte"
    assert "100.0 >= latency" in str(v_gte[0]["expression"])


def test_ast_timing_guard_chained_comparisons() -> None:
    """Verify detection of chained comparisons such as 0.0 < duration < 2.0."""
    code_chained = """
def test_chained():
    duration = 1.2
    assert 0.0 < duration < 2.0
"""
    violations = find_unmarked_wall_clock_assertions_in_source(
        code_chained, "test_chained.py"
    )
    assert len(violations) == 1
    assert violations[0]["function"] == "test_chained"


def test_ast_timing_guard_boolop_nested() -> None:
    """Verify detection of timing comparisons nested in boolean operations (and / or)."""
    code_and = """
def test_boolop_and():
    duration = 1.0
    status = 200
    assert status == 200 and duration < 2.0
"""
    v_and = find_unmarked_wall_clock_assertions_in_source(code_and, "test_bool.py")
    assert len(v_and) == 1
    assert v_and[0]["function"] == "test_boolop_and"

    code_nested = """
def test_boolop_nested():
    elapsed_time = 0.5
    ok = True
    assert ok and (2.0 > elapsed_time or False)
"""
    v_nested = find_unmarked_wall_clock_assertions_in_source(
        code_nested, "test_bool.py"
    )
    assert len(v_nested) == 1
    assert v_nested[0]["function"] == "test_boolop_nested"


def test_ast_timing_guard_binop_subtractions() -> None:
    """Verify detection of inline timing subtractions (monotonic() - t0 or end - start)."""
    code_monotonic = """
def test_direct_monotonic():
    t0 = 0.0
    assert time.monotonic() - t0 < 2.0
"""
    v_mono = find_unmarked_wall_clock_assertions_in_source(
        code_monotonic, "test_binop.py"
    )
    assert len(v_mono) == 1
    assert v_mono[0]["function"] == "test_direct_monotonic"

    code_diff = """
def test_time_diff():
    start_time = 0.0
    end_time = 1.0
    assert end_time - start_time < 2.0
"""
    v_diff = find_unmarked_wall_clock_assertions_in_source(code_diff, "test_binop.py")
    assert len(v_diff) == 1
    assert v_diff[0]["function"] == "test_time_diff"


def test_ast_timing_guard_wrapper_calls() -> None:
    """Verify detection of timing variables wrapped in round(), float(), int(), abs()."""
    code_round = """
def test_wrapped_round():
    duration = 1.456
    assert round(duration, 2) < 2.0
"""
    violations = find_unmarked_wall_clock_assertions_in_source(
        code_round, "test_wrap.py"
    )
    assert len(violations) == 1
    assert violations[0]["function"] == "test_wrapped_round"


def test_ast_timing_guard_expanded_timing_variables() -> None:
    """Verify detection of expanded timing variables (total_time, execution_time, etc.)."""
    vars_to_test = [
        "total_time",
        "execution_time",
        "query_time",
        "request_time",
        "process_time",
        "wall_time",
    ]
    for var_name in vars_to_test:
        code = f"""
def test_var_{var_name}():
    {var_name} = 1.0
    assert {var_name} < 2.0
"""
        violations = find_unmarked_wall_clock_assertions_in_source(
            code, f"test_{var_name}.py"
        )
        assert len(violations) == 1, f"Failed to detect timing variable: {var_name}"


def test_ast_timing_guard_subscript_access() -> None:
    """Verify detection of timing attributes in dict or json subscripts (res['duration'])."""
    code_dict = """
def test_dict_subscript():
    res = {"duration": 1.5, "latency_ms": 30.0}
    assert res["duration"] < 2.0
"""
    violations = find_unmarked_wall_clock_assertions_in_source(
        code_dict, "test_subscript.py"
    )
    assert len(violations) == 1
    assert violations[0]["function"] == "test_dict_subscript"


def test_ast_timing_guard_class_and_module_perf_exemptions() -> None:
    """Verify that class-level and module-level @pytest.mark.perf markers properly exempt tests."""
    # Class-level attribute marker
    code_class = """
@pytest.mark.perf
class TestSuitePerf:
    def test_latency(self):
        duration = 0.5
        assert duration < 2.0
"""
    assert (
        len(find_unmarked_wall_clock_assertions_in_source(code_class, "test_class.py"))
        == 0
    )

    # Class-level call marker
    code_class_call = """
@pytest.mark.perf(reason="benchmark")
class TestSuitePerfCall:
    def test_latency(self):
        duration = 0.5
        assert duration < 2.0
"""
    assert (
        len(
            find_unmarked_wall_clock_assertions_in_source(
                code_class_call, "test_class_call.py"
            )
        )
        == 0
    )

    # Module-level pytestmark = pytest.mark.perf
    code_module = """
pytestmark = pytest.mark.perf

def test_module_perf():
    duration = 0.5
    assert duration < 2.0
"""
    assert (
        len(
            find_unmarked_wall_clock_assertions_in_source(code_module, "test_module.py")
        )
        == 0
    )

    # Module-level list: pytestmark = [pytest.mark.perf]
    code_module_list = """
pytestmark = [pytest.mark.perf]

def test_module_perf_list():
    duration = 0.5
    assert duration < 2.0
"""
    assert (
        len(
            find_unmarked_wall_clock_assertions_in_source(
                code_module_list, "test_module_list.py"
            )
        )
        == 0
    )

    # Function-level direct import: @perf
    code_direct_perf = """
@perf
def test_direct_perf():
    duration = 0.5
    assert duration < 2.0
"""
    assert (
        len(
            find_unmarked_wall_clock_assertions_in_source(
                code_direct_perf, "test_direct_perf.py"
            )
        )
        == 0
    )


def test_ast_timing_guard_domain_attributes_not_flagged() -> None:
    """Verify that business domain model attributes (session.duration, ticket.duration) are not flagged."""
    code_business = """
def test_parking_duration_business_logic():
    session = get_mock_session()
    booking = get_mock_booking()
    contract = get_mock_contract()
    assert session.duration < 24
    assert booking.duration <= 8
    assert contract.duration < 365
"""
    violations = find_unmarked_wall_clock_assertions_in_source(
        code_business, "test_biz.py"
    )
    assert len(violations) == 0
