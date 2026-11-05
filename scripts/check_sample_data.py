#!/usr/bin/env python3
"""
StudyGraph Sample Data & Benchmark Validator (T02)

Validates the contents of the sample-data directory against manifest.csv:
1. Checks for missing files declared in manifest.csv.
2. Checks for untracked/extra files present on disk but absent in manifest.csv.
3. Checks for unsupported file formats.
4. Checks Quality Gate readiness (subjects, scanned notes, textbooks, exam papers).
"""

import csv
import os
import sys
from pathlib import Path

ALLOWED_TYPES = {"typed-pdf", "scanned", "ppt", "image", "textbook", "paper"}
ALLOWED_EXTENSIONS = {".pdf", ".pptx", ".ppt", ".png", ".jpg", ".jpeg"}
IGNORED_FILES = {
    ".gitkeep",
    "manifest.csv",
    "test_questions.csv",
    "link_labels.csv",
    "readme.md",
    ".ds_store",
    "thumbs.db",
}


def find_sample_data_dir() -> Path:
    """Find the sample-data directory from the script directory or current working directory."""
    cwd = Path.cwd()
    if (cwd / "sample-data").is_dir():
        return cwd / "sample-data"
    script_dir = Path(__file__).resolve().parent
    if (script_dir.parent / "sample-data").is_dir():
        return script_dir.parent / "sample-data"
    raise FileNotFoundError("Could not find sample-data directory.")


def check_benchmark_csvs(sample_data_dir: Path) -> dict:
    """Check the status of test_questions.csv and link_labels.csv."""
    results = {
        "test_questions_exists": False,
        "in_notes_count": 0,
        "out_of_notes_count": 0,
        "link_labels_exists": False,
        "link_labels_count": 0,
    }

    tq_path = sample_data_dir / "test_questions.csv"
    if tq_path.exists():
        results["test_questions_exists"] = True
        try:
            with open(tq_path, mode="r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    q_type = (row.get("question_type") or "").strip().lower()
                    if q_type == "in-notes":
                        results["in_notes_count"] += 1
                    elif q_type == "out-of-notes":
                        results["out_of_notes_count"] += 1
        except Exception as e:
            print(f"[!] Error reading test_questions.csv: {e}")

    ll_path = sample_data_dir / "link_labels.csv"
    if ll_path.exists():
        results["link_labels_exists"] = True
        try:
            with open(ll_path, mode="r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                results["link_labels_count"] = sum(1 for _ in reader)
        except Exception as e:
            print(f"[!] Error reading link_labels.csv: {e}")

    return results


def validate_sample_data(sample_data_dir: Path) -> int:
    """Main validation routine. Returns exit code (0 if all clear, 1 if issues found)."""
    manifest_path = sample_data_dir / "manifest.csv"
    if not manifest_path.exists():
        print(f"[ERROR] manifest.csv not found at: {manifest_path}")
        return 1

    print("=" * 70)
    print(" StudyGraph — Sample Data & Benchmark Validator")
    print(f" Directory: {sample_data_dir}")
    print("=" * 70)

    # 1. Read Manifest
    manifest_rows = []
    with open(manifest_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        required_cols = {"file_name", "subject", "module", "type", "notes"}
        if not required_cols.issubset(set(reader.fieldnames or [])):
            print(f"[ERROR] manifest.csv missing required headers. Found: {reader.fieldnames}")
            print(f"        Required: {sorted(list(required_cols))}")
            return 1
        for row_idx, row in enumerate(reader, start=2):
            fname = (row.get("file_name") or "").strip()
            if fname:
                manifest_rows.append((row_idx, row))

    manifest_filenames = {row["file_name"].strip() for _, row in manifest_rows}

    # 2. Scan Disk for all non-template files
    disk_files_by_name = {}
    unsupported_disk_files = []

    for root, dirs, files in os.walk(sample_data_dir):
        for f in files:
            if f.lower() in IGNORED_FILES or f.startswith("."):
                continue
            full_path = Path(root) / f
            rel_path = full_path.relative_to(sample_data_dir)
            disk_files_by_name[f] = rel_path
            if full_path.suffix.lower() not in ALLOWED_EXTENSIONS:
                unsupported_disk_files.append((f, rel_path, full_path.suffix))

    # 3. Check Manifest Rows against Disk
    missing_files = []
    type_errors = []
    found_manifest_files = []

    subjects_found = set()
    types_found = set()

    print("\n--- Manifest Inventory Check ---")
    for row_idx, row in manifest_rows:
        fname = row["file_name"].strip()
        subject = row["subject"].strip()
        module = row["module"].strip()
        ftype = row["type"].strip().lower()

        # Validate type enum
        if ftype not in ALLOWED_TYPES:
            type_errors.append((row_idx, fname, ftype))

        # Expected relative paths
        expected_candidates = []
        if ftype == "paper":
            expected_candidates.append(Path("papers") / fname)
            expected_candidates.append(Path(subject) / "papers" / fname)
        elif module:
            expected_candidates.append(Path(subject) / module / fname)
        expected_candidates.append(Path(subject) / fname)
        expected_candidates.append(Path(fname))

        # Check existence on disk
        if fname in disk_files_by_name:
            actual_rel_path = disk_files_by_name[fname]
            found_manifest_files.append(fname)
            subjects_found.add(subject)
            types_found.add(ftype)
            print(f" [OK]      {fname} -> Found at {actual_rel_path}")
        else:
            primary_expected = expected_candidates[0] if expected_candidates else Path(fname)
            missing_files.append((fname, primary_expected))
            print(f" [MISSING] {fname} -> Expected at {primary_expected}")

    # 4. Check for Untracked Files on Disk
    untracked_files = []
    for fname, rel_path in disk_files_by_name.items():
        if fname not in manifest_filenames:
            untracked_files.append((fname, rel_path))

    if untracked_files:
        print("\n--- Untracked Files on Disk (Not in manifest.csv) ---")
        for fname, rel_path in untracked_files:
            print(f" [UNTRACKED] {rel_path} (Please register this in manifest.csv)")

    if unsupported_disk_files:
        print("\n--- Unsupported File Formats on Disk ---")
        for fname, rel_path, ext in unsupported_disk_files:
            print(f" [UNSUPPORTED] {rel_path} (Extension '{ext}' not in {sorted(list(ALLOWED_EXTENSIONS))})")

    if type_errors:
        print("\n--- Manifest Type Errors ---")
        for row_idx, fname, bad_type in type_errors:
            print(f" [INVALID TYPE] Row {row_idx}: '{fname}' has type '{bad_type}' (Allowed: {sorted(list(ALLOWED_TYPES))})")

    # 5. Quality Gate Readiness Check
    print("\n--- Quality Gate Readiness Checklist ---")
    gate_checks = []

    # Subjects check (>= 2 subjects for cross-subject graph)
    subject_count = len(subjects_found)
    gate_checks.append((
        f"Subjects represented: {subject_count} (Found: {', '.join(sorted(subjects_found)) or 'None'})",
        subject_count >= 2,
        "Target: At least 2 subjects needed for cross-subject links (Gates G01, G09)"
    ))

    # Scanned notes check (for OCR gate G03)
    has_scanned = bool({"scanned", "image"}.intersection(types_found))
    gate_checks.append((
        f"Scanned / handwritten notes present: {'Yes' if has_scanned else 'No'}",
        has_scanned,
        "Target: Scanned notes required for Vision OCR accuracy gate (G03)"
    ))

    # Textbook check
    has_textbook = "textbook" in types_found
    gate_checks.append((
        f"Reference textbook present: {'Yes' if has_textbook else 'No'}",
        has_textbook,
        "Target: 1 textbook needed for notes-vs-textbook feature (F17)"
    ))

    # Exam papers count (>= 3 papers)
    paper_count = sum(1 for _, row in manifest_rows if row["type"].strip().lower() == "paper" and row["file_name"].strip() in disk_files_by_name)
    gate_checks.append((
        f"Exam papers on disk: {paper_count}",
        paper_count >= 3,
        "Target: At least 3 previous-year exam papers needed for repeated questions (F19, R05)"
    ))

    # Benchmark CSVs check
    bench = check_benchmark_csvs(sample_data_dir)
    gate_checks.append((
        f"test_questions.csv in-notes questions: {bench['in_notes_count']}",
        bench['in_notes_count'] >= 20,
        "Target: 20 in-notes questions required for Chatbot Citation gate (G04)"
    ))
    gate_checks.append((
        f"test_questions.csv out-of-notes questions: {bench['out_of_notes_count']}",
        bench['out_of_notes_count'] >= 10,
        "Target: 10 out-of-notes questions required for Chatbot Honesty gate (G05)"
    ))
    gate_checks.append((
        f"link_labels.csv rows prepared: {bench['link_labels_count']}",
        bench['link_labels_count'] >= 50,
        "Target: 50 links template required for Link Precision human evaluation (G01)"
    ))

    for label, status_ok, note in gate_checks:
        icon = "[PASS]" if status_ok else "[PENDING]"
        print(f" {icon:9} {label}")
        if not status_ok:
            print(f"           -> {note}")

    # Summary
    print("\n" + "=" * 70)
    print(" SUMMARY REPORT")
    print(f" - Manifest declared files : {len(manifest_rows)}")
    print(f" - Files found on disk     : {len(found_manifest_files)}")
    print(f" - Files missing on disk   : {len(missing_files)}")
    print(f" - Untracked files on disk : {len(untracked_files)}")
    print(f" - Format errors           : {len(unsupported_disk_files) + len(type_errors)}")
    print("=" * 70)

    # Return status: 0 if no missing, untracked, or format errors; 1 otherwise
    if missing_files or untracked_files or unsupported_disk_files or type_errors:
        return 1
    return 0


if __name__ == "__main__":
    try:
        sample_dir = find_sample_data_dir()
        exit_code = validate_sample_data(sample_dir)
        sys.exit(exit_code)
    except Exception as exc:
        print(f"[FATAL] Validator failed with unexpected error: {exc}")
        sys.exit(2)

