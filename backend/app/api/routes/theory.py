"""
Theory View API Routes for StudyGraph (Task T12).
Relies on:
  - Feature F10: Theory view per subject with cross-module link chips.
  - Risk R04: UX grounded in bite-sized cards and navigable links.
  - Decision D04: Python with FastAPI.
  - Decision D05: PostgreSQL on Supabase.
  - RULEBOOK Section 13 Rule 3: Max 4-line explanation + real-world use.
  - RULEBOOK Section 13 Rule 8: Weak links hidden by default.
  - RULEBOOK Section 13 Rule 9: Visible 'unreviewed' markings.
  - RULEBOOK Rule 11: Multi-user privacy isolation.
"""

from collections import defaultdict
import logging
from typing import Dict, List
from fastapi import APIRouter, Depends, HTTPException, status
import psycopg2.extras

from backend.app.api.deps import CurrentUser, get_current_user
from backend.app.database import get_db_cursor
from backend.app.schemas.theory import (
    SubjectTheoryResponse,
    TheoryLinkChip,
    TheoryModuleGroup,
    TheorySourceCitation,
    TheoryTopicCard,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/subjects", tags=["Theory"])


@router.get(
    "/{subject_id}/theory",
    response_model=SubjectTheoryResponse,
    summary="Get structured revision cards grouped by module with cross-module link chips",
)
def get_subject_theory(
    subject_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Returns all academic topic cards for a subject, grouped strictly by module.
    Each card contains:
      - Keyword
      - Max 4-line explanation
      - Real-world application
      - Unreviewed badge flag
      - Connected relationship chips (cross-module flagged, weak links flagged)
    Enforces Rule 11 (Student Privacy): Only returns topics for subjects owned by the student.
    """
    with get_db_cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        # Step 1: Verify subject ownership and read source_preference (Feature F17)
        cur.execute(
            """
            SELECT id, name, COALESCE(source_preference, 'notes') AS source_preference
            FROM subjects
            WHERE id = %s AND user_id = %s;
            """,
            (subject_id, current_user.id),
        )
        subject_row = cur.fetchone()
        if not subject_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subject not found or access denied.",
            )

        subject_name = subject_row["name"]
        source_preference = subject_row.get("source_preference") or "notes"
        if source_preference not in ("notes", "textbook"):
            source_preference = "notes"

        # Step 2: Fetch all topics for this subject (with source citations)
        cur.execute(
            """
            SELECT 
                t.id, 
                t.subject_id, 
                t.keyword, 
                t.explanation, 
                t.real_world_use, 
                t.module_no, 
                t.reviewed,
                COALESCE(t.source_variants, '{}'::jsonb) AS source_variants,
                c.label AS cluster_label,
                COALESCE(src.citations_json, '[]'::json) AS source_citations
            FROM topics t
            LEFT JOIN clusters c ON t.cluster_id = c.id
            LEFT JOIN (
                SELECT
                    ts.topic_id,
                    JSON_AGG(
                        DISTINCT JSONB_BUILD_OBJECT(
                            'filename', d.filename,
                            'page', COALESCE(ch.page, 1),
                            'source_kind', d.source_kind
                        )
                    ) AS citations_json
                FROM topic_sources ts
                JOIN chunks ch ON ch.id = ts.chunk_id
                JOIN documents d ON d.id = ch.document_id
                WHERE d.source_kind IN ('notes', 'textbook')
                GROUP BY ts.topic_id
            ) src ON src.topic_id = t.id
            WHERE t.subject_id = %s
            ORDER BY COALESCE(t.module_no, 1) ASC, t.keyword ASC;
            """,
            (subject_id,),
        )
        topic_rows = cur.fetchall() or []

        if not topic_rows:
            return SubjectTheoryResponse(
                subject_id=subject_id,
                subject_name=subject_name,
                source_preference=source_preference,
                total_topics=0,
                total_links=0,
                unreviewed_count=0,
                modules=[],
            )

        topic_ids = [str(r["id"]) for r in topic_rows]

        # Step 3: Fetch all active edges connected to any of these topics
        cur.execute(
            """
            SELECT 
                e.id, 
                e.topic_a, 
                e.topic_b, 
                e.type, 
                e.reason, 
                e.industry_example, 
                e.strength, 
                e.scope,
                ta.id AS a_id,
                ta.keyword AS a_keyword,
                COALESCE(ta.module_no, 1) AS a_module_no,
                sa.name AS a_subject_name,
                tb.id AS b_id,
                tb.keyword AS b_keyword,
                COALESCE(tb.module_no, 1) AS b_module_no,
                sb.name AS b_subject_name
            FROM edges e
            JOIN topics ta ON ta.id = e.topic_a
            JOIN topics tb ON tb.id = e.topic_b
            LEFT JOIN subjects sa ON sa.id = ta.subject_id
            LEFT JOIN subjects sb ON sb.id = tb.subject_id
            WHERE e.status != 'deleted'
              AND (e.topic_a = ANY(%s::uuid[]) OR e.topic_b = ANY(%s::uuid[]))
            ORDER BY e.strength DESC;
            """,
            (topic_ids, topic_ids),
        )
        edge_rows = cur.fetchall() or []

    # Step 4: Map edges into chips per topic
    chips_by_topic: Dict[str, List[TheoryLinkChip]] = defaultdict(list)
    total_distinct_edges = set()

    for edge in edge_rows:
        edge_id = str(edge["id"])
        total_distinct_edges.add(edge_id)
        a_id = str(edge["a_id"])
        b_id = str(edge["b_id"])
        strength = int(edge["strength"])
        is_weak = strength < 3

        # If topic A is one of our subject's topics, add chip pointing to B
        if a_id in topic_ids:
            is_cross_mod = edge["a_module_no"] != edge["b_module_no"]
            is_cross_sub = (edge["scope"] == "cross_subject") or (edge["a_subject_name"] != edge["b_subject_name"])
            chips_by_topic[a_id].append(
                TheoryLinkChip(
                    edge_id=edge_id,
                    target_topic_id=b_id,
                    target_keyword=edge["b_keyword"],
                    target_module_no=edge["b_module_no"],
                    target_subject_name=edge["b_subject_name"],
                    type=edge["type"],
                    reason=edge["reason"],
                    industry_example=edge["industry_example"],
                    strength=strength,
                    is_cross_module=is_cross_mod,
                    is_cross_subject=is_cross_sub,
                    is_weak=is_weak,
                    direction="outgoing",
                )
            )

        # If topic B is one of our subject's topics, add chip pointing to A
        if b_id in topic_ids:
            is_cross_mod = edge["a_module_no"] != edge["b_module_no"]
            is_cross_sub = (edge["scope"] == "cross_subject") or (edge["a_subject_name"] != edge["b_subject_name"])
            chips_by_topic[b_id].append(
                TheoryLinkChip(
                    edge_id=edge_id,
                    target_topic_id=a_id,
                    target_keyword=edge["a_keyword"],
                    target_module_no=edge["a_module_no"],
                    target_subject_name=edge["a_subject_name"],
                    type=edge["type"],
                    reason=edge["reason"],
                    industry_example=edge["industry_example"],
                    strength=strength,
                    is_cross_module=is_cross_mod,
                    is_cross_subject=is_cross_sub,
                    is_weak=is_weak,
                    direction="incoming",
                )
            )

    # Step 5: Group topics by module
    modules_map: Dict[int, List[TheoryTopicCard]] = defaultdict(list)
    unreviewed_count = 0

    for tr in topic_rows:
        tid = str(tr["id"])
        is_reviewed = bool(tr["reviewed"])
        if not is_reviewed:
            unreviewed_count += 1

        mod_no = int(tr["module_no"]) if tr["module_no"] is not None else 1

        # Resolve active source kind & explanation according to subject source_preference (Feature F17)
        variants = tr.get("source_variants") if isinstance(tr.get("source_variants"), dict) else {}
        raw_cits = tr.get("source_citations") or []
        topic_cits = [
            TheorySourceCitation(
                filename=c["filename"],
                page=int(c.get("page") or 1),
                source_kind=c.get("source_kind") or "notes",
            )
            for c in raw_cits
            if isinstance(c, dict) and c.get("filename")
        ]
        available_kinds = {c.source_kind for c in topic_cits} | {k for k in variants.keys() if k in ("notes", "textbook")}
        has_multiple = len(available_kinds) > 1

        if source_preference in available_kinds:
            active_kind: str | None = source_preference
        elif available_kinds:
            active_kind = "notes" if "notes" in available_kinds else sorted(available_kinds)[0]
        else:
            active_kind = None

        explanation_out = tr["explanation"]
        real_world_out = tr["real_world_use"]
        if active_kind and active_kind in variants and isinstance(variants[active_kind], dict):
            v = variants[active_kind]
            if v.get("explanation"):
                explanation_out = v["explanation"]
            if v.get("real_world_use") is not None:
                real_world_out = v["real_world_use"]

        # Order citations so preferred/active source appears first
        ordered_cits = sorted(
            topic_cits,
            key=lambda c: (c.source_kind != active_kind, c.filename, c.page),
        )

        # Sort chips: cross-module first, then by strength desc
        sorted_chips = sorted(
            chips_by_topic.get(tid, []),
            key=lambda c: (not c.is_cross_module, -c.strength, c.target_keyword),
        )

        card = TheoryTopicCard(
            id=tid,
            subject_id=str(tr["subject_id"]),
            keyword=tr["keyword"],
            explanation=explanation_out,
            real_world_use=real_world_out,
            module_no=mod_no,
            reviewed=is_reviewed,
            cluster_label=tr["cluster_label"],
            active_source_kind=active_kind,
            has_multiple_sources=has_multiple,
            source_citations=ordered_cits,
            links=sorted_chips,
        )
        modules_map[mod_no].append(card)

    module_groups: List[TheoryModuleGroup] = []
    for mod_no in sorted(modules_map.keys()):
        cards = modules_map[mod_no]
        module_groups.append(
            TheoryModuleGroup(
                module_no=mod_no,
                module_title=f"Module {mod_no}",
                topic_count=len(cards),
                topics=cards,
            )
        )

    return SubjectTheoryResponse(
        subject_id=subject_id,
        subject_name=subject_name,
        source_preference=source_preference,
        total_topics=len(topic_rows),
        total_links=len(total_distinct_edges),
        unreviewed_count=unreviewed_count,
        modules=module_groups,
    )

