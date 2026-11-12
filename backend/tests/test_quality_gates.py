"""
Automated Pytest Suite for Quality Gates (Task T19).
Verifies that quality gate runner measures all 10 gates truthfully and generates QUALITY_REPORT.md.
Relies on:
  - Decision D14: pytest testing framework.
  - docs/QUALITY_GATES.md: G01 to G10.
  - docs/RISKS.md: R03, R06, R07, R08, R10, R14, R17, R19.
"""

from pathlib import Path
import pytest
from backend.scripts.run_quality_gates import QualityGateRunner

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


def test_quality_gate_runner_initialization():
    runner = QualityGateRunner()
    assert runner.sample_data_dir.exists(), "sample-data directory must exist"


def test_g01_link_precision_measurement():
    runner = QualityGateRunner()
    res = runner.measure_g01_link_precision()
    assert res.gate_id == "G01"
    assert res.direction == ">="
    assert res.target == 0.85
    # Measured precision on hand-labeled links
    assert res.actual >= 0.85, f"G01 link precision {res.actual} should be >= 0.85"


def test_g02_evidence_completeness_measurement():
    runner = QualityGateRunner()
    res = runner.measure_g02_evidence_completeness()
    assert res.gate_id == "G02"
    assert res.target == 1.0
    assert res.actual == 1.0, f"All valid links must have reason and 2 snippets (Rule 13.1, G02)"


def test_g03_scanned_topic_accuracy_measurement():
    runner = QualityGateRunner()
    res = runner.measure_g03_scanned_topic_accuracy()
    assert res.gate_id == "G03"
    assert res.target == 0.80
    assert res.actual >= 0.80, f"G03 scanned topic accuracy {res.actual} should be >= 0.80"


def test_g04_chatbot_citation_accuracy():
    runner = QualityGateRunner()
    res = runner.measure_g04_chatbot_citations()
    assert res.gate_id == "G04"
    assert res.target == 0.90
    assert res.actual >= 0.90, f"G04 citation rate {res.actual} should be >= 0.90"


def test_g05_chatbot_honesty_disclaimer():
    runner = QualityGateRunner()
    res = runner.measure_g05_chatbot_honesty()
    assert res.gate_id == "G05"
    assert res.target == 0.90
    assert res.actual >= 0.90, f"G05 honesty disclaimer rate {res.actual} should be >= 0.90"


def test_run_all_and_report_generation(tmp_path):
    runner = QualityGateRunner()
    results = runner.run_all()
    assert len(results) == 10, "Must evaluate exactly 10 quality gates (G01 - G10)"

    gate_ids = [r.gate_id for r in results]
    for expected_id in ["G01", "G02", "G03", "G04", "G05", "G06", "G07", "G08", "G09", "G10"]:
        assert expected_id in gate_ids, f"Gate {expected_id} missing from results"

    md = runner.generate_report_markdown()
    assert "# QUALITY REPORT" in md
    assert "G01" in md and "G10" in md
    assert "Ethical Engineering Principle" in md

