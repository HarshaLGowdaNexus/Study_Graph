"""
Automated Fix Script for Quality Gate G06 (Duplicate Topics).
Merges verified semantic duplicate and synonym topic pairs within the same subject.
Uses DedupeService.merge_topics to:
  1. Re-wire edges pointing to merged topic
  2. Transfer all topic_sources (no lost citations)
  3. Record merged keyword into topic_aliases
  4. Write audit entry into topic_merges with merge_type='manual'
"""

import sys
from pathlib import Path
from uuid import UUID

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.app.database import get_db_cursor
from backend.app.services.dedupe_service import DedupeService

# Exact list of verified duplicate topic pairs to merge: (surviving_id, merged_id, surviving_kw, merged_kw, sim)
PAIRS_TO_MERGE = [
    (
        UUID("5821c3a9-7a3a-4606-855e-89ae32d137ad"),
        UUID("3351547e-1709-46d0-83f1-66f739120fc5"),
        "Computer Networks",
        "Computer Networks",
        0.9524,
    ),
    (
        UUID("e4f212a6-d95f-4b21-8dd4-3ed77e27a659"),
        UUID("87efed98-0807-4b6d-886b-4233820c4232"),
        "System Views of Operating Systems",
        "System Views of Operating System",
        0.9388,
    ),
    (
        UUID("7e08b589-05c4-40da-af7e-076abaac107c"),
        UUID("8b31b398-94e2-479e-9691-6ceadbaceffa"),
        "Dual Mode of Operation",
        "Dual-Mode Operation",
        0.8971,
    ),
    (
        UUID("0ed7cc7f-e09d-4596-87d0-c7eb067516b9"),
        UUID("1c272c72-b24b-45fa-9220-09222620d843"),
        "Prototyping",
        "Software Prototyping",
        0.8619,
    ),
]


def run_g06_fix():
    print("=" * 70)
    print("APPLYING FIX FOR QUALITY GATE G06: DUPLICATE TOPIC MERGES")
    print("=" * 70)

    dedupe_service = DedupeService()
    merges_done = 0

    for surviving_id, merged_id, surv_kw, merg_kw, sim in PAIRS_TO_MERGE:
        print(f"Merging: '{merg_kw}' ({merged_id}) -> '{surv_kw}' ({surviving_id}) [sim={sim:.4f}]...")
        try:
            result = dedupe_service.merge_topics(
                surviving_topic_id=surviving_id,
                merged_topic_id=merged_id,
                similarity_score=sim,
                merge_type="manual",
            )
            print(f"  OK: Merged successfully (merge_id: {result['merge_id']})")
            merges_done += 1
        except Exception as e:
            print(f"  ERROR: {e}")

    print("=" * 70)
    print(f"Successfully completed {merges_done} topic merges.")
    print("=" * 70)


if __name__ == "__main__":
    run_g06_fix()
