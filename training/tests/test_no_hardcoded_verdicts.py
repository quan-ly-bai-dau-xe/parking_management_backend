"""Anti-Facade Scanner using Python AST analysis to detect hardcoded verification verdicts."""

import ast
import re
from pathlib import Path

import nbformat
import pytest

FORBIDDEN_VERDICT_VALUES = {
    "PASS",
    "FAIL",
    "VERIFIED",
    "VERIFIED_NON_TRAINING",
    "IDENTICAL",
    "0.00%",
}

TARGET_VARIABLE_NAMES = {
    "status",
    "verdict",
    "verification_status",
}

FORBIDDEN_PRINT_PATTERNS = {
    "PASS",
    "VERIFIED",
    "status: PASS",
    "status: VERIFIED",
    "verdict: PASS",
    "verdict: VERIFIED",
}

MARKDOWN_TABLE_FORBIDDEN_REGEX = re.compile(
    r"\|\s*0\.00%\s*\|\s*\*\*IDENTICAL\*\*\s*\|"
)


class VerdictASTVisitor(ast.NodeVisitor):
    """AST Visitor that traverses Python syntax trees to detect hardcoded verdict literals."""

    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.violations: list[str] = []

    def visit_Assign(self, node: ast.Assign) -> None:
        """Detect static literal assignments like status = 'PASS'."""
        for target in node.targets:
            if (
                isinstance(target, ast.Name)
                and target.id in TARGET_VARIABLE_NAMES
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
                and node.value.value in FORBIDDEN_VERDICT_VALUES
            ):
                self.violations.append(
                    f"[{self.filename}:{node.lineno}] Hardcoded verdict assignment to variable "
                    f"'{target.id}' = '{node.value.value}'"
                )
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """Detect annotated literal assignments like status: str = 'PASS'."""
        if (
            isinstance(node.target, ast.Name)
            and node.target.id in TARGET_VARIABLE_NAMES
            and node.value
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
            and node.value.value in FORBIDDEN_VERDICT_VALUES
        ):
            self.violations.append(
                f"[{self.filename}:{node.lineno}] Hardcoded annotated verdict assignment to variable "
                f"'{node.target.id}' = '{node.value.value}'"
            )
        self.generic_visit(node)

    def visit_Dict(self, node: ast.Dict) -> None:
        """Detect hardcoded dictionary keys like {'status': 'VERIFIED_NON_TRAINING'}."""
        for key, value in zip(node.keys, node.values, strict=False):
            if (
                key
                and isinstance(key, ast.Constant)
                and isinstance(key.value, str)
                and key.value in TARGET_VARIABLE_NAMES
                and value
                and isinstance(value, ast.Constant)
                and isinstance(value.value, str)
                and value.value in FORBIDDEN_VERDICT_VALUES
            ):
                self.violations.append(
                    f"[{self.filename}:{node.lineno}] Hardcoded dictionary verdict entry "
                    f"'{key.value}': '{value.value}'"
                )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Detect print statements outputting fixed verdict banners."""
        if isinstance(node.func, ast.Name) and node.func.id == "print":
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    val_clean = arg.value.strip()
                    if (
                        val_clean in FORBIDDEN_VERDICT_VALUES
                        or val_clean in FORBIDDEN_PRINT_PATTERNS
                    ):
                        self.violations.append(
                            f"[{self.filename}:{node.lineno}] Hardcoded verdict print statement: '{val_clean}'"
                        )
        self.generic_visit(node)


def scan_python_code(source: str, filename: str) -> list[str]:
    """Parse and scan Python source code for hardcoded verdicts."""
    violations: list[str] = []

    # 1. Check markdown/text patterns inside comments or multiline strings
    for line_no, line in enumerate(source.splitlines(), start=1):
        if MARKDOWN_TABLE_FORBIDDEN_REGEX.search(line):
            violations.append(
                f"[{filename}:{line_no}] Hardcoded markdown table verdict pattern matched: '{line.strip()}'"
            )

    # 2. Parse AST and scan code nodes
    try:
        tree = ast.parse(source, filename=filename)
        visitor = VerdictASTVisitor(filename)
        visitor.visit(tree)
        violations.extend(visitor.violations)
    except SyntaxError as err:
        violations.append(f"[{filename}] SyntaxError during AST parsing: {err}")

    return violations


def scan_notebook_file(notebook_path: Path) -> list[str]:
    """Scan all markdown and code cells of a Jupyter notebook."""
    nb = nbformat.read(notebook_path, as_version=4)
    violations: list[str] = []

    for cell_idx, cell in enumerate(nb.cells):
        cell_id = cell.get("id", f"idx_{cell_idx}")
        cell_name = f"{notebook_path.name} [cell {cell_idx} id:{cell_id}]"

        if cell.cell_type == "markdown":
            for line_no, line in enumerate(cell.source.splitlines(), start=1):
                if MARKDOWN_TABLE_FORBIDDEN_REGEX.search(line):
                    violations.append(
                        f"[{cell_name}:{line_no}] Hardcoded markdown table verdict in cell: '{line.strip()}'"
                    )
        elif cell.cell_type == "code":
            cell_violations = scan_python_code(cell.source, cell_name)
            violations.extend(cell_violations)

    return violations


# ==============================================================================
# Mutation Tests (Red-then-Green proofs for the scanner itself)
# ==============================================================================


@pytest.mark.unit
def test_anti_facade_scanner_mutation_red_variable_assignment() -> None:
    """Test scanner catches injected hardcoded variable assignment (Pha Đỏ)."""
    snippet = """
def check_pipeline():
    status = "PASS"
    return status
"""
    violations = scan_python_code(snippet, "injected_test.py")
    assert len(violations) == 1
    assert "assignment to variable 'status' = 'PASS'" in violations[0]


@pytest.mark.unit
def test_anti_facade_scanner_mutation_red_dict_literal() -> None:
    """Test scanner catches injected hardcoded dictionary verdict entry (Pha Đỏ)."""
    snippet = """
def export_metadata():
    return {
        "model": "cct_xs",
        "status": "VERIFIED_NON_TRAINING",
    }
"""
    violations = scan_python_code(snippet, "injected_test.py")
    assert len(violations) == 1
    assert "dictionary verdict entry 'status': 'VERIFIED_NON_TRAINING'" in violations[0]


@pytest.mark.unit
def test_anti_facade_scanner_mutation_red_print_statement() -> None:
    """Test scanner catches injected print statement with fixed verdict banner (Pha Đỏ)."""
    snippet = """
def log_result():
    print("status: PASS")
"""
    violations = scan_python_code(snippet, "injected_test.py")
    assert len(violations) == 1
    assert "Hardcoded verdict print statement: 'status: PASS'" in violations[0]


@pytest.mark.unit
def test_anti_facade_scanner_mutation_red_markdown_table() -> None:
    """Test scanner catches injected markdown table with static IDENTICAL verdict (Pha Đỏ)."""
    snippet = (
        '"""\n'
        "# Audit Summary\n"
        "| Epoch | Diff | Verdict |\n"
        "| 1 | 0.00% | **IDENTICAL** |\n"
        '"""\n'
    )
    violations = scan_python_code(snippet, "injected_test.py")
    assert len(violations) == 1
    assert "Hardcoded markdown table verdict pattern matched" in violations[0]


@pytest.mark.unit
def test_anti_facade_scanner_mutation_red_notebook_cell(tmp_path: Path) -> None:
    """Test scanner catches hardcoded verdict injected into a notebook code cell (Pha Đỏ)."""
    nb = nbformat.v4.new_notebook()
    nb.cells.append(
        nbformat.v4.new_code_cell(
            source="verdict = 'VERIFIED'\nprint('Done')",
            id="mut_cell_1",
        )
    )
    nb_file = tmp_path / "test_mut.ipynb"
    with open(nb_file, "w", encoding="utf-8") as f:
        nbformat.write(nb, f)

    violations = scan_notebook_file(nb_file)
    assert len(violations) == 1
    assert (
        "Hardcoded verdict assignment to variable 'verdict' = 'VERIFIED'"
        in violations[0]
    )


# ==============================================================================
# Green Test: Full Codebase Verification (0 hardcoded verdicts)
# ==============================================================================


@pytest.mark.unit
def test_codebase_has_zero_hardcoded_verdicts() -> None:
    """
    Scan all Python files in training/scripts/, training/src/plate_training/,
    and all cells in training/notebooks/kaggle_train.ipynb to confirm 0 hardcoded verdicts.
    """
    root_dir = Path(__file__).resolve().parent.parent

    target_paths: list[Path] = []
    # 1. Scripts
    target_paths.extend((root_dir / "scripts").glob("*.py"))
    # 2. Library source code
    target_paths.extend((root_dir / "src" / "plate_training").rglob("*.py"))

    all_violations: list[str] = []
    for py_file in target_paths:
        code_text = py_file.read_text(encoding="utf-8")
        violations = scan_python_code(code_text, str(py_file))
        all_violations.extend(violations)

    # 3. Kaggle Training Notebook
    nb_path = root_dir / "notebooks" / "kaggle_train.ipynb"
    assert nb_path.is_file(), f"Notebook not found at {nb_path}"
    nb_violations = scan_notebook_file(nb_path)
    all_violations.extend(nb_violations)

    assert all_violations == [], (
        f"Found {len(all_violations)} hardcoded verdict violations in codebase:\n"
        + "\n".join(f" - {v}" for v in all_violations)
    )
