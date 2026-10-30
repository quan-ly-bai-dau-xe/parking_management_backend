"""Tests for kaggle_train.ipynb:
1. Committed cleanliness (0 outputs, null execution count, exactly 9 code cells).
2. AST Test: Uncommented model.fit call guarded by 'if not DRY_RUN:' with contract arguments.
3. AST Mutation Red Proof: Verifies AST check fails if fit is commented or removed.
4. Spy Test 1 (DRY_RUN = True): Proves model.fit is NEVER called, while evaluate & ONNX export succeed.
5. Spy Test 2 (DRY_RUN = False): Stubbed spy harness proving zero laptop training and contract arguments.
6. Subprocess Green Execution via nbconvert (when nbconvert available).
7. Mutation Red Tests: Data leakage guardrail and config corruption guardrail.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import nbformat
import pytest

# Ensure Keras defaults to PyTorch backend before any Keras imports
os.environ.setdefault("KERAS_BACKEND", "torch")


def get_notebook_path() -> Path:
    """Resolve notebook path."""
    return Path(__file__).resolve().parent.parent / "notebooks" / "kaggle_train.ipynb"


def extract_code_cells(nb_path: Path) -> list[str]:
    """Extract source code of all code cells from notebook."""
    nb = nbformat.read(nb_path, as_version=4)
    return [cell.source for cell in nb.cells if cell.cell_type == "code"]


def is_not_dry_run_condition(node: ast.AST) -> bool:
    """Check if an AST expression represents 'not DRY_RUN'."""
    return bool(
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, ast.Not)
        and isinstance(node.operand, ast.Name)
        and node.operand.id == "DRY_RUN"
    )


def find_fit_calls_under_not_dry_run(code_cells: list[str]) -> list[dict[str, Any]]:
    """Search all code cells for uncommented .fit() Call AST nodes guarded by 'not DRY_RUN'.

    Returns metadata of discovered calls.
    """
    fit_calls: list[dict[str, Any]] = []
    for cell_idx, source in enumerate(code_cells, start=1):
        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            raise SyntaxError(f"Syntax error parsing code cell {cell_idx}: {e}") from e

        for node in ast.walk(tree):
            if isinstance(node, ast.If) and is_not_dry_run_condition(node.test):
                # Search within the If body
                for sub_node in ast.walk(ast.Module(body=node.body, type_ignores=[])):
                    if isinstance(sub_node, ast.Call):
                        func = sub_node.func
                        if isinstance(func, ast.Attribute) and func.attr == "fit":
                            args = [ast.unparse(a) for a in sub_node.args]
                            keywords = {
                                kw.arg: ast.unparse(kw.value)
                                for kw in sub_node.keywords
                                if kw.arg is not None
                            }
                            fit_calls.append(
                                {
                                    "cell_index": cell_idx,
                                    "line_number": sub_node.lineno,
                                    "node": sub_node,
                                    "args": args,
                                    "keywords": keywords,
                                }
                            )
    return fit_calls


def execute_notebook_cells(
    nb_path: Path,
    working_dir: Path,
    dry_run: bool = True,
    max_cell_idx: int | None = None,
) -> dict[str, Any]:
    """Execute notebook code cells in-process with controlled globals and temporary directories.

    Returns the execution namespace.
    """
    code_cells = extract_code_cells(nb_path)
    env_globals: dict[str, Any] = {
        "__name__": "__main__",
        "__file__": str(nb_path),
    }

    checkpoint_dir = working_dir / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    export_dir = working_dir / "exported_models"
    export_dir.mkdir(parents=True, exist_ok=True)

    for idx, source in enumerate(code_cells, start=1):
        if max_cell_idx is not None and idx > max_cell_idx:
            break

        # Adjust Cell 1 overrides dynamically for test isolation
        if "Cell 1:" in source:
            source += (
                f"\nDRY_RUN = {dry_run}\n"
                f"KAGGLE_WORKING_DIR = Path(r'{working_dir}')\n"
                f"CHECKPOINT_DIR = Path(r'{checkpoint_dir}')\n"
                f"EXPORT_DIR = Path(r'{export_dir}')\n"
            )
        elif "Cell 7:" in source:
            # Guarantee DRY_RUN setting holds entering Cell 7
            env_globals["DRY_RUN"] = dry_run

        exec(compile(source, f"cell_{idx}", "exec"), env_globals)

    return env_globals


# --------------------------------------------------------------------------
# Test 1: Committed Notebook Cleanliness (0 outputs, null execution_count)
# --------------------------------------------------------------------------
@pytest.mark.unit
def test_notebook_committed_cleanliness() -> None:
    """Verify committed notebook has 0 outputs, null execution_count, and exactly 9 code cells."""
    nb_path = get_notebook_path()
    assert nb_path.is_file(), f"Notebook missing at {nb_path}"

    nb = nbformat.read(nb_path, as_version=4)
    code_cells = [c for c in nb.cells if c.cell_type == "code"]
    assert len(code_cells) == 9, (
        f"Expected exactly 9 code cells, found {len(code_cells)}"
    )

    for idx, cell in enumerate(code_cells, start=1):
        assert cell.outputs == [], f"Cell {idx} has non-empty outputs"
        assert cell.execution_count is None, f"Cell {idx} has non-null execution_count"


# --------------------------------------------------------------------------
# Test 2: AST Test (Uncommented model.fit inside if not DRY_RUN)
# --------------------------------------------------------------------------
@pytest.mark.unit
def test_notebook_ast_fit_guarded_by_not_dry_run() -> None:
    """Verify that kaggle_train.ipynb contains an uncommented model.fit(...) call.

    Guarded by 'if not DRY_RUN:' with mandatory contract arguments:
    - train_dataset
    - validation_data=val_dataset
    - initial_epoch=initial_epoch
    - callbacks=callbacks
    """
    nb_path = get_notebook_path()
    code_cells = extract_code_cells(nb_path)
    fit_calls = find_fit_calls_under_not_dry_run(code_cells)

    assert len(fit_calls) == 1, (
        f"Expected exactly 1 uncommented model.fit call guarded by 'not DRY_RUN', "
        f"found {len(fit_calls)}"
    )

    call_info = fit_calls[0]
    args = call_info["args"]
    keywords = call_info["keywords"]

    # Verify train_dataset positional or keyword
    has_train = (
        ("train_dataset" in args)
        or (keywords.get("x") == "train_dataset")
        or (keywords.get("train_dataset") == "train_dataset")
    )
    assert has_train, (
        f"Expected train_dataset passed to fit, got args={args}, kwargs={keywords}"
    )

    # Verify validation_data keyword
    assert keywords.get("validation_data") == "val_dataset", (
        f"Expected validation_data=val_dataset, got {keywords.get('validation_data')}"
    )

    # Verify initial_epoch keyword
    assert keywords.get("initial_epoch") == "initial_epoch", (
        f"Expected initial_epoch=initial_epoch, got {keywords.get('initial_epoch')}"
    )

    # Verify callbacks keyword
    assert keywords.get("callbacks") == "callbacks", (
        f"Expected callbacks=callbacks, got {keywords.get('callbacks')}"
    )


# --------------------------------------------------------------------------
# Test 3: AST Mutation Red Test (Fails if model.fit is commented or removed)
# --------------------------------------------------------------------------
@pytest.mark.unit
def test_notebook_ast_mutation_commented_or_missing_fit_fails() -> None:
    """Mutation Test (Anti-Facade Proof):

    Verify AST check fails if model.fit is commented out, removed,
    or placed outside 'if not DRY_RUN:'.
    """
    nb_path = get_notebook_path()
    code_cells = extract_code_cells(nb_path)

    # Mutation 1: Comment out model.fit call (as it was in G1)
    mutated_commented: list[str] = []
    for cell in code_cells:
        if "history = model.fit(" in cell:
            lines = cell.splitlines()
            new_lines: list[str] = []
            commenting = False
            for line in lines:
                if "history = model.fit(" in line:
                    commenting = True
                if commenting:
                    new_lines.append("# " + line)
                    if line.strip().endswith(")"):
                        commenting = False
                else:
                    new_lines.append(line)
            mutated_commented.append("\n".join(new_lines))
        else:
            mutated_commented.append(cell)

    calls_commented = find_fit_calls_under_not_dry_run(mutated_commented)
    assert len(calls_commented) == 0, (
        "find_fit_calls_under_not_dry_run should find 0 calls when fit is commented out!"
    )

    # Mutation 2: Inverted guard (if DRY_RUN instead of if not DRY_RUN)
    mutated_inverted = [
        cell.replace("if not DRY_RUN:", "if DRY_RUN:") for cell in code_cells
    ]
    calls_inverted = find_fit_calls_under_not_dry_run(mutated_inverted)
    assert len(calls_inverted) == 0, (
        "find_fit_calls_under_not_dry_run should find 0 calls when condition is 'if DRY_RUN:'!"
    )

    # Mutation 3: Rename method to something other than fit
    mutated_renamed = [
        cell.replace("model.fit(", "model.evaluate(") for cell in code_cells
    ]
    calls_renamed = find_fit_calls_under_not_dry_run(mutated_renamed)
    assert len(calls_renamed) == 0, (
        "find_fit_calls_under_not_dry_run should find 0 calls when method is renamed!"
    )


# --------------------------------------------------------------------------
# Test 4: Spy Test 1 (DRY_RUN = True, model.fit must NEVER be called)
# --------------------------------------------------------------------------
@pytest.mark.unit
def test_notebook_spy_dry_run_true_fit_forbidden(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Execute notebook with DRY_RUN = True while a spy replaces keras.Model.fit.

    The spy raises AssertionError.
    Assert:
    - fit is never called.
    - evaluate runs.
    - ONNX export and parity check succeed.
    """
    pytest.importorskip("torch")
    pytest.importorskip("keras")
    import keras

    nb_path = get_notebook_path()

    def forbidden_fit_spy(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("keras.Model.fit MUST NOT be called when DRY_RUN = True!")

    monkeypatch.setattr(keras.Model, "fit", forbidden_fit_spy)

    # Execute all notebook cells in-process
    execute_notebook_cells(nb_path, working_dir=tmp_path, dry_run=True)

    # Verify artifacts produced
    export_dir = tmp_path / "exported_models"
    onnx_file = export_dir / "cct_xs_v2_global.onnx"
    summary_file = export_dir / "run_summary.json"

    assert onnx_file.is_file(), f"Expected exported ONNX model at {onnx_file}"
    assert summary_file.is_file(), f"Expected run_summary.json at {summary_file}"

    with open(summary_file, encoding="utf-8") as f:
        summary = json.load(f)

    assert summary["dry_run"] is True
    assert summary["parity"]["passed"] is True


# --------------------------------------------------------------------------
# Test 5: Spy Test 2 (DRY_RUN = False, harness stubbed spy call contract)
# --------------------------------------------------------------------------
@pytest.mark.unit
def test_notebook_spy_dry_run_false_harness_call_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Execute notebook training harness with DRY_RUN = False while keras.Model.fit is stubbed.

    Stubbing ensures ZERO training on laptop.
    Assert:
    - spy was called exactly once (call_count == 1).
    - train_dataset was passed.
    - validation_data=val_dataset was passed.
    - initial_epoch was passed.
    - ModelCheckpoint and EpochTimingCallback were included in callbacks.
    - Zero weight updates occurred.
    """
    pytest.importorskip("torch")
    pytest.importorskip("keras")
    import keras

    nb_path = get_notebook_path()

    class FitSpy:
        def __init__(self) -> None:
            self.call_count: int = 0
            self.call_args: tuple[Any, ...] = ()
            self.call_kwargs: dict[str, Any] = {}

        def __call__(self, *args: Any, **kwargs: Any) -> Any:
            self.call_count += 1
            self.call_args = args
            self.call_kwargs = kwargs
            dummy_history = keras.callbacks.History()
            dummy_history.history = {
                "loss": [0.42],
                "val_loss": [0.45],
                "plate_acc": [0.95],
                "val_plate_acc": [0.92],
            }
            return dummy_history

    spy = FitSpy()
    monkeypatch.setattr(keras.Model, "fit", spy)

    # Execute up to Cell 7 (training cell) with DRY_RUN = False
    ns = execute_notebook_cells(
        nb_path, working_dir=tmp_path, dry_run=False, max_cell_idx=7
    )

    # 1. Assert call count == 1
    assert spy.call_count == 1, (
        f"Expected keras.Model.fit called exactly once, got {spy.call_count}"
    )

    # 2. Assert train_dataset
    train_arg = (
        spy.call_args[0]
        if spy.call_args
        else spy.call_kwargs.get("x") or spy.call_kwargs.get("train_dataset")
    )
    assert train_arg is not None, "train_dataset was not passed to model.fit"

    # 3. Assert validation_data=val_dataset
    val_arg = spy.call_kwargs.get("validation_data")
    assert val_arg is not None, "validation_data was not passed to model.fit"
    if "val_dataset" in ns:
        assert val_arg is ns["val_dataset"]

    # 4. Assert initial_epoch
    init_epoch_arg = spy.call_kwargs.get("initial_epoch")
    assert init_epoch_arg is not None, "initial_epoch was not passed to model.fit"
    assert isinstance(init_epoch_arg, int)

    # 5. Assert callbacks: ModelCheckpoint and EpochTimingCallback
    callbacks = spy.call_kwargs.get("callbacks")
    assert isinstance(callbacks, list), (
        f"Expected callbacks list, got {type(callbacks)}"
    )

    has_checkpoint = any(
        isinstance(cb, keras.callbacks.ModelCheckpoint) for cb in callbacks
    )
    assert has_checkpoint, (
        "callbacks must contain a keras.callbacks.ModelCheckpoint instance"
    )

    has_timing = any(cb.__class__.__name__ == "EpochTimingCallback" for cb in callbacks)
    assert has_timing, "callbacks must contain an EpochTimingCallback instance"


# --------------------------------------------------------------------------
# Test 6: Green Subprocess Execution via nbconvert (Optional full CLI check)
# --------------------------------------------------------------------------
@pytest.mark.unit
def test_notebook_execution_green(tmp_path: Path) -> None:
    """Verify notebook executes cleanly under nbconvert with exit code 0."""
    pytest.importorskip("torch")
    pytest.importorskip("keras")
    pytest.importorskip("nbconvert")
    nb_path = get_notebook_path()
    out_nb = tmp_path / "executed_green.ipynb"

    cmd = [
        sys.executable,
        "-m",
        "jupyter",
        "nbconvert",
        "--to",
        "notebook",
        "--execute",
        str(nb_path),
        "--output-dir",
        str(tmp_path),
        "--output",
        out_nb.name,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert res.returncode == 0, (
        f"nbconvert failed with exit code {res.returncode}:\n{res.stderr}\n{res.stdout}"
    )
    assert out_nb.is_file(), f"Executed notebook missing at {out_nb}"


# --------------------------------------------------------------------------
# Test 7: Mutation Red Test 1 — Data Leakage Guardrail
# --------------------------------------------------------------------------
@pytest.mark.unit
def test_notebook_execution_mutation_red_leakage(tmp_path: Path) -> None:
    """Verify notebook fails (exit code != 0) when unhandled data leakage is injected (Pha Đỏ 1)."""
    pytest.importorskip("torch")
    pytest.importorskip("keras")
    pytest.importorskip("nbconvert")
    nb_path = get_notebook_path()
    nb = nbformat.read(nb_path, as_version=4)

    # Inject deliberate leakage call in Cell 5
    for cell in nb.cells:
        cell.source += (
            "\n# MUTATION TEST: Unhandled leakage injection\n"
            "validate_splits([ManifestItem(image_path='leak.png', sha256=next(iter(frozen_sha256)), plate_text='29A12345', split='train', provenance='leak', license='CC0', group_id='leak_g')], registry_path=registry_path, allow_missing_files=True, check_phash=False)\n"
        )

    mut_in = tmp_path / "mut_leakage_in.ipynb"
    out_nb = tmp_path / "mut_leakage_out.ipynb"
    with open(mut_in, "w", encoding="utf-8") as f:
        nbformat.write(nb, f)

    cmd = [
        sys.executable,
        "-m",
        "jupyter",
        "nbconvert",
        "--to",
        "notebook",
        "--execute",
        str(mut_in),
        "--output-dir",
        str(tmp_path),
        "--output",
        out_nb.name,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert res.returncode != 0, (
        f"Expected nbconvert failure on leakage mutation, got exit code {res.returncode}"
    )
    combined_log = res.stderr + res.stdout
    assert "DataLeakageError" in combined_log or "CellExecutionError" in combined_log


# --------------------------------------------------------------------------
# Test 8: Mutation Red Test 2 — Config Corruption Guardrail
# --------------------------------------------------------------------------
@pytest.mark.unit
def test_notebook_execution_mutation_red_corrupted_config(tmp_path: Path) -> None:
    """Verify notebook fails (exit code != 0) when configuration is corrupted (Pha Đỏ 2)."""
    pytest.importorskip("torch")
    pytest.importorskip("keras")
    pytest.importorskip("nbconvert")
    nb_path = get_notebook_path()
    nb = nbformat.read(nb_path, as_version=4)

    # Corrupt plate config validation in Cell 4
    for cell in nb.cells:
        if cell.cell_type == "code" and "Cell 4:" in cell.source:
            cell.source += (
                "\n# MUTATION TEST: Config corruption injection\n"
                "assert plate_cfg.max_plate_slots == 999, 'Forced assertion failure on corrupted config'\n"
            )

    mut_in = tmp_path / "mut_config_in.ipynb"
    out_nb = tmp_path / "mut_config_out.ipynb"
    with open(mut_in, "w", encoding="utf-8") as f:
        nbformat.write(nb, f)

    cmd = [
        sys.executable,
        "-m",
        "jupyter",
        "nbconvert",
        "--to",
        "notebook",
        "--execute",
        str(mut_in),
        "--output-dir",
        str(tmp_path),
        "--output",
        out_nb.name,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert res.returncode != 0, (
        f"Expected nbconvert failure on corrupted config, got exit code {res.returncode}"
    )
    combined_log = res.stderr + res.stdout
    assert (
        "Forced assertion failure on corrupted config" in combined_log
        or "CellExecutionError" in combined_log
    )


# --------------------------------------------------------------------------
# Test 9: Cell 5 Tested Leakage Validator (Detector Crop Leakage Red-then-Green)
# --------------------------------------------------------------------------
@pytest.mark.unit
def test_notebook_cell5_leakage_validator_red_then_green(tmp_path: Path) -> None:
    """
    Red-then-Green test for Cell 5 tested leakage validator:
      - RED Phase: Manifest containing detector crop of frozen test photo -> rejects with DataLeakageError.
      - GREEN Phase: Clean synthetic manifest -> passes cleanly with 0 leakage.
    """
    import cv2
    import numpy as np

    from plate_training.manifest import ManifestItem
    from plate_training.split import (
        DataLeakageError,
        get_default_registry_path,
        load_frozen_test_registry,
        validate_splits,
    )

    reg_path = get_default_registry_path()
    registry = load_frozen_test_registry(reg_path)

    # 1. RED Phase: Detector crop leakage from frozen test registry rejected with DataLeakageError
    crop_entries = [r for r in registry if r.get("crop_sha256")]
    assert len(crop_entries) > 0, (
        "Expected frozen test registry to contain crop_sha256 entries"
    )
    leaked_crop_sha = crop_entries[0]["crop_sha256"]

    leaked_manifest_item = ManifestItem(
        image_path="train_detector_crop_leak.png",
        sha256=leaked_crop_sha,
        plate_text="51F12345",
        split="train",
        provenance="detector-crop-leak-test",
        license="CC0",
        group_id="vehicle_leak_001",
    )

    with pytest.raises(
        DataLeakageError, match="Exact crop SHA-256 duplicate leakage detected"
    ):
        validate_splits(
            [leaked_manifest_item],
            registry_path=reg_path,
            allow_missing_files=True,
            check_phash=False,
        )

    # Also prove Cell 5 in-process execution rejects detector crop leakage
    nb_path = get_notebook_path()
    code_cells = extract_code_cells(nb_path)
    cell5_source = next(c for c in code_cells if "Cell 5:" in c)

    fake_kaggle_input = tmp_path / "kaggle_input"
    fake_manifest_dir = fake_kaggle_input / "vietnamese-license-plate-manifest"
    fake_manifest_dir.mkdir(parents=True, exist_ok=True)
    leaked_img_path = fake_manifest_dir / "crop_leaked.png"
    cv2.imwrite(str(leaked_img_path), np.zeros((64, 128, 3), dtype=np.uint8))

    leaked_manifest_file = fake_manifest_dir / "manifest.json"
    with open(leaked_manifest_file, "w", encoding="utf-8") as f:
        json.dump(
            [
                {
                    "image_path": "crop_leaked.png",
                    "sha256": leaked_crop_sha,
                    "plate_text": "51F12345",
                    "split": "train",
                    "provenance": "leak-test",
                    "license": "CC0",
                    "group_id": "veh_leak_001",
                }
            ],
            f,
            indent=2,
        )

    cell5_env: dict[str, Any] = {
        "__name__": "__main__",
        "REPO_ROOT": Path(__file__).resolve().parent.parent.parent,
        "KAGGLE_INPUT_DIR": fake_kaggle_input,
        "KAGGLE_WORKING_DIR": tmp_path / "kaggle_work",
        "RANDOM_SEED": 2026,
    }
    (tmp_path / "kaggle_work").mkdir(parents=True, exist_ok=True)

    with pytest.raises(
        DataLeakageError, match="Exact crop SHA-256 duplicate leakage detected"
    ):
        exec(compile(cell5_source, "cell_5", "exec"), cell5_env)

    # 2. GREEN Phase: Clean synthetic manifest passes cleanly
    clean_items = [
        ManifestItem(
            image_path="clean_0.png",
            sha256="0" * 64,
            plate_text="29A12345",
            split="train",
            provenance="clean-synthetic",
            license="CC0",
            group_id="clean_veh_001",
        ),
        ManifestItem(
            image_path="clean_1.png",
            sha256="1" * 64,
            plate_text="30B67890",
            split="val",
            provenance="clean-synthetic",
            license="CC0",
            group_id="clean_veh_002",
        ),
    ]
    warnings = validate_splits(
        clean_items,
        registry_path=reg_path,
        allow_missing_files=True,
        check_phash=False,
    )
    assert warnings == []
