"""
Report Integrity Fixtures and Mutation Verification Test Suite.

Verifies verify_report_integrity.py behavior against:
1. Fake URL injection (detected as non-zero failures).
2. Fabricated quote mismatch (detected as non-zero failures).
3. Forbidden V-word token injection (strictly rejected).
4. Unregistered inline code token injection (detected in unmatched count).
5. CLI process exit codes (0 for pristine, non-zero for mutated report).
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

from tests.tools.verify_report_integrity import verify_report

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture(autouse=True)
def ensure_sample_data() -> None:
    """Override conftest db fixture: no database needed for report integrity unit tests."""
    return None


FALLBACK_PRISTINE_REPORT = """# Baseline Report

| Document | URL | HTTP Status | Publisher | Access Date | Verbatim Quote |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Thông tư 79/2024/TT-BCA | https://vanban.chinhphu.vn/?pageid=27160&docid=211945 | 200 OK | Cổng TTĐT Chính phủ | 2026-10-20 | 79-bca.signed.pdf |
| ONNX Runtime Threading | https://onnxruntime.ai/docs/performance/tune-performance/threading.html | 200 OK | Microsoft ONNX Runtime | 2026-10-20 | Controls whether additional INTRA or INTER threads spin waiting for work. |

References:
- Model: `PlateBlacklist`
- App: `parking`
- Field: `license_plate`
- File: `README.md`
- Token: `id`
"""


class TestReportIntegrityFuzzingFixtures:
    """
    Mutation Testing and Fuzzing for verify_report_integrity.py.
    Injects fake URLs, fake quotes, forbidden words, and fake tokens into isolated report copies.
    """

    @pytest.fixture
    def pristine_report_text(self) -> str:
        for name in (
            "round40_final_report.md",
            "round39_final_report.md",
            "round38_final_report.md",
        ):
            p = REPO_ROOT / ".agents" / name
            if p.exists():
                return p.read_text(encoding="utf-8")
        return FALLBACK_PRISTINE_REPORT

    @pytest.mark.network
    def test_baseline_pristine_report_passes(self) -> None:
        """The actual production report passes with strictly 0 failures and 0 unmatched tokens."""
        r40 = REPO_ROOT / ".agents" / "round40_final_report.md"
        r39 = REPO_ROOT / ".agents" / "round39_final_report.md"
        report_path = r40 if r40.exists() else r39
        if not report_path.exists():
            pytest.skip(
                "Neither round40_final_report.md nor round39_final_report.md exists; skips until report generation"
            )
        failures = verify_report(report_path)
        assert failures == 0, f"Expected 0 failures on pristine report, got {failures}"

    @pytest.mark.network
    def test_adversarial_mutation_fake_url_detected(
        self, pristine_report_text: str
    ) -> None:
        """
        Injecting a non-existent fake URL into an isolated temporary copy
        must be caught by verify_report with total_failures > 0.
        """
        fake_table_row = (
            "| Fake Law | https://example.com/fake-circular-nonexistent-999-2026 "
            "| 200 OK | Fake Gazettes | 2026-10-20 | Fabricated article quote |\n"
        )
        if "| Thông tư 79/2024/TT-BCA" in pristine_report_text:
            mutated_text = pristine_report_text.replace(
                "| Thông tư 79/2024/TT-BCA",
                fake_table_row + "| Thông tư 79/2024/TT-BCA",
            )
        elif "| Thông tư số 79/2024/TT-BCA" in pristine_report_text:
            mutated_text = pristine_report_text.replace(
                "| Thông tư số 79/2024/TT-BCA",
                fake_table_row + "| Thông tư số 79/2024/TT-BCA",
            )
        else:
            mutated_text = pristine_report_text + "\n" + fake_table_row

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", encoding="utf-8", delete=False
        ) as tmp:
            tmp.write(mutated_text)
            tmp_path = Path(tmp.name)

        try:
            failures = verify_report(tmp_path)
            assert failures > 0, (
                "verify_report MUST fail when a fake URL citation is injected!"
            )
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    @pytest.mark.network
    def test_adversarial_mutation_fabricated_quote_detected(
        self, pristine_report_text: str
    ) -> None:
        """
        Injecting a fabricated quote for an otherwise valid 200 OK URL
        must be caught as a QUOTE MISMATCH with total_failures > 0.
        """
        # Replace the verified ONNX quote with a fabricated claim
        mutated_text = pristine_report_text.replace(
            "Controls whether additional INTRA or INTER threads spin waiting for work.",
            "This is a completely fabricated quote about neural network spinning that does not exist.",
        )

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", encoding="utf-8", delete=False
        ) as tmp:
            tmp.write(mutated_text)
            tmp_path = Path(tmp.name)

        try:
            failures = verify_report(tmp_path)
            assert failures > 0, "verify_report MUST fail on fabricated quote mismatch!"
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def test_adversarial_mutation_forbidden_v_word_detected(
        self, pristine_report_text: str
    ) -> None:
        """
        Injecting the forbidden 7-letter V-word must raise an AssertionError
        or terminate verification immediately with non-zero failures.
        """
        mutated_text = pristine_report_text + "\nWe celebrate our V" + "ictory here.\n"

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", encoding="utf-8", delete=False
        ) as tmp:
            tmp.write(mutated_text)
            tmp_path = Path(tmp.name)

        try:
            with pytest.raises(AssertionError, match="Found forbidden word"):
                verify_report(tmp_path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def test_adversarial_mutation_fake_code_token_detected(
        self, pristine_report_text: str
    ) -> None:
        """
        Injecting a dynamically generated unknown inline code token (not in schema, django registry, or corpus)
        must be caught in UNMATCHED_COUNT with total_failures > 0.
        """
        dynamic_fake_token = f"dyn_unmatched_token_{uuid.uuid4().hex}"
        mutated_text = (
            pristine_report_text
            + f"\nAdversarial test injection: `{dynamic_fake_token}`\n"
        )

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", encoding="utf-8", delete=False
        ) as tmp:
            tmp.write(mutated_text)
            tmp_path = Path(tmp.name)

        try:
            failures = verify_report(tmp_path)
            assert failures > 0, (
                "verify_report MUST fail when an unregistered code token is injected!"
            )
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def test_adversarial_cli_process_exit_codes(
        self, pristine_report_text: str
    ) -> None:
        """
        Verify CLI exit code behavior:
        - Pristine report returns exit code 0.
        - Mutated report returns non-zero exit code.
        """
        script_path = str(REPO_ROOT / "tests" / "tools" / "verify_report_integrity.py")
        r40 = REPO_ROOT / ".agents" / "round40_final_report.md"
        r39 = REPO_ROOT / ".agents" / "round39_final_report.md"

        # 1. Clean report exit code 0
        if r40.exists():
            clean_target = str(r40)
            tmp_clean = None
        elif r39.exists():
            clean_target = str(r39)
            tmp_clean = None
        else:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".md", encoding="utf-8", delete=False
            ) as tmp:
                tmp.write(FALLBACK_PRISTINE_REPORT)
                clean_target = tmp.name
                tmp_clean = clean_target

        try:
            cmd_clean = [sys.executable, script_path, clean_target, "--offline"]
            res_clean = subprocess.run(
                cmd_clean,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(REPO_ROOT),
            )
            assert res_clean.returncode == 0, (
                f"Clean report failed: {res_clean.stderr}\n{res_clean.stdout}"
            )
            assert (
                "FINAL INTEGRITY VERIFICATION RESULT: TOTAL_FAILURES=0"
                in res_clean.stdout
            )
        finally:
            if tmp_clean and os.path.exists(tmp_clean):
                os.remove(tmp_clean)

        # 2. Mutated report with fake token exit code 1
        dyn_bad_token = f"cli_bad_token_{uuid.uuid4().hex}"
        active_report = r40 if r40.exists() else (r39 if r39.exists() else None)
        base_clean = (
            active_report.read_text(encoding="utf-8")
            if active_report is not None
            else FALLBACK_PRISTINE_REPORT
        )
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", encoding="utf-8", delete=False
        ) as tmp:
            tmp.write(base_clean + f"\nInjected bad token: `{dyn_bad_token}`\n")
            bad_path = tmp.name

        try:
            res_bad = subprocess.run(
                [sys.executable, script_path, bad_path, "--offline"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(REPO_ROOT),
            )
            assert res_bad.returncode != 0, (
                "Mutated report CLI call MUST return non-zero exit code!"
            )
            assert "Unmatched Tokens Count:" in res_bad.stdout
            assert "TOTAL_FAILURES=" in res_bad.stdout
        finally:
            if os.path.exists(bad_path):
                os.remove(bad_path)
