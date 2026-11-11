"""
Graph Compilation, Versioning & Caching Service for StudyGraph.
Relies on:
  - Decision D03: react-force-graph (2D/3D) data structure ({ nodes, links }).
  - Decision D05: PostgreSQL storage with JSONB caching.
  - Decision D12: Local-first cache fallback for offline demo safety (R17).
  - Pipeline Step 12 & 14: Version snapshot creation and graph caching.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import psycopg2.extras

from backend.app.core.config import settings
from backend.app.database import get_db_cursor

logger = logging.getLogger(__name__)


class GraphService:
    """
    Assembles graph networks, tracks versions with human-readable diff summaries,
    and caches pre-compiled graph JSON for zero-latency retrieval and offline demo reliability.
    """

    def __init__(self):
        self.local_cache_dir = Path(settings.ROOT_DIR) / ".storage_cache" / "graphs"
        self.local_cache_dir.mkdir(parents=True, exist_ok=True)

    def assemble_subject_graph(self, subject_id: str, user_id: str) -> Dict[str, Any]:
        """
        Compiles the complete graph data (nodes, links, clusters, metrics)
        for a specific subject folder.
        """
        with get_db_cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            # 1. Fetch subject details
            cursor.execute(
                "SELECT id, name, source_preference FROM subjects WHERE id = %s AND user_id = %s;",
                (subject_id, user_id),
            )
            subj = cursor.fetchone()
            if not subj:
                raise ValueError(f"Subject {subject_id} not found for user {user_id}")

            subject_name = subj["name"]

            # 2. Fetch all topics for this subject with cluster labels
            cursor.execute(
                """
                SELECT 
                    t.id, 
                    t.keyword, 
                    t.explanation, 
                    t.real_world_use, 
                    t.module_no, 
                    t.reviewed,
                    t.cluster_id,
                    c.label AS cluster_label,
                    pc.id AS parent_cluster_id,
                    pc.label AS parent_cluster_label
                FROM topics t
                LEFT JOIN clusters c ON t.cluster_id = c.id
                LEFT JOIN clusters pc ON c.parent_id = pc.id
                WHERE t.subject_id = %s
                ORDER BY t.module_no ASC, t.keyword ASC;
                """,
                (subject_id,),
            )
            topics = cursor.fetchall()

            # 3. Fetch all active edges (exclude soft-deleted)
            topic_ids = [str(t["id"]) for t in topics]
            edges = []
            if topic_ids:
                cursor.execute(
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
                        e.status, 
                        e.locked, 
                        e.graph_version
                    FROM edges e
                    WHERE e.status != 'deleted'
                      AND (e.topic_a = ANY(%s::uuid[]) OR e.topic_b = ANY(%s::uuid[]));
                    """,
                    (topic_ids, topic_ids),
                )
                edges = cursor.fetchall()

            # 4. Fetch edge evidence snippets
            edge_ids = [str(e["id"]) for e in edges]
            evidence_by_edge: Dict[str, List[Dict[str, Any]]] = {}
            if edge_ids:
                cursor.execute(
                    """
                    SELECT edge_id, chunk_id, snippet
                    FROM edge_evidence
                    WHERE edge_id = ANY(%s::uuid[]);
                    """,
                    (edge_ids,),
                )
                evidence_rows = cursor.fetchall()
                for ev in evidence_rows:
                    eid = str(ev["edge_id"])
                    evidence_by_edge.setdefault(eid, []).append({
                        "chunk_id": str(ev["chunk_id"]) if ev["chunk_id"] else None,
                        "snippet": ev["snippet"],
                    })

            # 5. Fetch cluster hierarchy
            cursor.execute(
                """
                SELECT id, parent_id, label
                FROM clusters
                WHERE subject_id = %s
                ORDER BY parent_id NULLS FIRST, label ASC;
                """,
                (subject_id,),
            )
            cluster_rows = cursor.fetchall()

        # Format nodes for react-force-graph
        nodes = []
        for t in topics:
            nodes.append({
                "id": str(t["id"]),
                "name": t["keyword"],
                "keyword": t["keyword"],
                "explanation": t["explanation"],
                "real_world_use": t.get("real_world_use") or "",
                "module_no": t.get("module_no") or 1,
                "reviewed": bool(t.get("reviewed")),
                "cluster_id": str(t["cluster_id"]) if t.get("cluster_id") else None,
                "cluster_label": t.get("cluster_label") or "Unclustered",
                "parent_cluster_label": t.get("parent_cluster_label") or t.get("cluster_label") or "Core",
                "subject_id": subject_id,
                "subject_name": subject_name,
            })

        # Format links for react-force-graph
        links = []
        for e in edges:
            eid = str(e["id"])
            links.append({
                "id": eid,
                "source": str(e["topic_a"]),
                "target": str(e["topic_b"]),
                "type": e["type"],
                "reason": e["reason"],
                "industry_example": e["industry_example"],
                "strength": int(e["strength"]),
                "scope": e["scope"],
                "status": e["status"],
                "locked": bool(e["locked"]),
                "graph_version": e.get("graph_version") or 1,
                "evidence": evidence_by_edge.get(eid, []),
            })

        # Assemble cluster tree
        clusters_tree = []
        top_clusters = [c for c in cluster_rows if not c["parent_id"]]
        for parent in top_clusters:
            pid = str(parent["id"])
            subs = [
                {"id": str(c["id"]), "label": c["label"]}
                for c in cluster_rows
                if c["parent_id"] and str(c["parent_id"]) == pid
            ]
            clusters_tree.append({
                "id": pid,
                "label": parent["label"],
                "sub_clusters": subs,
            })

        return {
            "subject_id": subject_id,
            "subject_name": subject_name,
            "scope": "subject",
            "nodes": nodes,
            "links": links,
            "clusters": clusters_tree,
            "stats": {
                "node_count": len(nodes),
                "link_count": len(links),
                "cluster_count": len(clusters_tree),
            },
        }

    def assemble_cross_subject_graph(self, user_id: str) -> Dict[str, Any]:
        """
        Compiles the holistic multi-subject 3D graph connecting all topics
        and cross-subject bridges across all folders owned by the student.
        """
        with get_db_cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            # 1. Fetch all subjects for this student
            cursor.execute(
                "SELECT id, name FROM subjects WHERE user_id = %s ORDER BY name ASC;",
                (user_id,),
            )
            subj_rows = cursor.fetchall()
            subject_map = {str(s["id"]): s["name"] for s in subj_rows}
            user_subject_ids = list(subject_map.keys())

            if not user_subject_ids:
                return {
                    "scope": "cross_subject",
                    "nodes": [],
                    "links": [],
                    "subjects": [],
                    "stats": {"node_count": 0, "link_count": 0},
                }

            # 2. Fetch all topics across all student subjects
            cursor.execute(
                """
                SELECT 
                    t.id, 
                    t.subject_id,
                    t.keyword, 
                    t.explanation, 
                    t.real_world_use, 
                    t.module_no, 
                    t.reviewed,
                    t.cluster_id,
                    c.label AS cluster_label
                FROM topics t
                LEFT JOIN clusters c ON t.cluster_id = c.id
                WHERE t.subject_id = ANY(%s::uuid[])
                ORDER BY t.subject_id, t.keyword ASC;
                """,
                (user_subject_ids,),
            )
            topics = cursor.fetchall()

            # 3. Fetch all edges between these topics
            topic_ids = [str(t["id"]) for t in topics]
            edges = []
            evidence_by_edge: Dict[str, List[Dict[str, Any]]] = {}
            if topic_ids:
                cursor.execute(
                    """
                    SELECT 
                        id, topic_a, topic_b, type, reason, industry_example, 
                        strength, scope, status, locked, graph_version
                    FROM edges
                    WHERE status != 'deleted'
                      AND topic_a = ANY(%s::uuid[])
                      AND topic_b = ANY(%s::uuid[]);
                    """,
                    (topic_ids, topic_ids),
                )
                edges = cursor.fetchall()

                # Fetch edge evidence snippets (RULEBOOK: no evidence, no link)
                edge_ids = [str(e["id"]) for e in edges]
                if edge_ids:
                    cursor.execute(
                        """
                        SELECT edge_id, chunk_id, snippet
                        FROM edge_evidence
                        WHERE edge_id = ANY(%s::uuid[]);
                        """,
                        (edge_ids,),
                    )
                    evidence_rows = cursor.fetchall()
                    for ev in evidence_rows:
                        eid = str(ev["edge_id"])
                        evidence_by_edge.setdefault(eid, []).append({
                            "chunk_id": str(ev["chunk_id"]) if ev["chunk_id"] else None,
                            "snippet": ev["snippet"],
                        })

        topic_lookup = {str(t["id"]): t for t in topics}

        nodes = [
            {
                "id": str(t["id"]),
                "name": t["keyword"],
                "keyword": t["keyword"],
                "explanation": t["explanation"],
                "real_world_use": t.get("real_world_use") or "",
                "module_no": t.get("module_no") or 1,
                "reviewed": bool(t.get("reviewed")),
                "cluster_label": t.get("cluster_label") or "General",
                "subject_id": str(t["subject_id"]),
                "subject_name": subject_map.get(str(t["subject_id"]), "Subject"),
            }
            for t in topics
        ]

        links = []
        for e in edges:
            eid = str(e["id"])
            t_a = topic_lookup.get(str(e["topic_a"]))
            t_b = topic_lookup.get(str(e["topic_b"]))

            source_subj_id = str(t_a["subject_id"]) if t_a else ""
            target_subj_id = str(t_b["subject_id"]) if t_b else ""
            source_subj_name = subject_map.get(source_subj_id, "Unknown Subject")
            target_subj_name = subject_map.get(target_subj_id, "Unknown Subject")

            is_cross = (source_subj_id != target_subj_id) or (e.get("scope") == "cross_subject")
            scope = "cross_subject" if is_cross else "same_subject"
            ev_list = evidence_by_edge.get(eid, [])

            links.append({
                "id": eid,
                "source": str(e["topic_a"]),
                "target": str(e["topic_b"]),
                "source_keyword": t_a["keyword"] if t_a else "Unknown Topic",
                "target_keyword": t_b["keyword"] if t_b else "Unknown Topic",
                "source_subject_id": source_subj_id,
                "target_subject_id": target_subj_id,
                "source_subject_name": source_subj_name,
                "target_subject_name": target_subj_name,
                "type": e["type"],
                "reason": e["reason"],
                "industry_example": e["industry_example"],
                "strength": int(e["strength"]),
                "scope": scope,
                "status": e["status"],
                "locked": bool(e["locked"]),
                "evidence": ev_list,
                "snippet_a": ev_list[0]["snippet"] if len(ev_list) > 0 else None,
                "snippet_b": ev_list[1]["snippet"] if len(ev_list) > 1 else None,
            })

        return {
            "scope": "cross_subject",
            "subjects": [{"id": sid, "name": sname} for sid, sname in subject_map.items()],
            "nodes": nodes,
            "links": links,
            "stats": {
                "node_count": len(nodes),
                "link_count": len(links),
                "cross_subject_links": sum(1 for e in links if e["scope"] == "cross_subject"),
            },
        }

    def record_graph_version(
        self,
        user_id: str,
        subject_id: Optional[str],
        summary: str,
    ) -> Dict[str, Any]:
        """
        Creates a new immutable snapshot record in 'graph_versions'.
        Calculates the next incremental version number for the student.
        """
        with get_db_cursor() as cursor:
            # Determine next version number
            if subject_id:
                cursor.execute(
                    """
                    SELECT COALESCE(MAX(version_number), 0) + 1
                    FROM graph_versions
                    WHERE user_id = %s AND subject_id = %s;
                    """,
                    (user_id, subject_id),
                )
            else:
                cursor.execute(
                    """
                    SELECT COALESCE(MAX(version_number), 0) + 1
                    FROM graph_versions
                    WHERE user_id = %s;
                    """,
                    (user_id,),
                )
            next_version = cursor.fetchone()[0]

            cursor.execute(
                """
                INSERT INTO graph_versions (user_id, subject_id, version_number, summary)
                VALUES (%s, %s, %s, %s)
                RETURNING id, created_at;
                """,
                (user_id, subject_id, next_version, summary),
            )
            v_row = cursor.fetchone()
            version_id = str(v_row[0])
            created_at = v_row[1].isoformat() if hasattr(v_row[1], "isoformat") else str(v_row[1])

        logger.info(
            f"[GraphService] Created graph version {next_version} for user {user_id} "
            f"(subject={subject_id}): '{summary}'"
        )

        return {
            "version_id": version_id,
            "version_number": next_version,
            "created_at": created_at,
            "summary": summary,
        }

    def refresh_and_cache_graph(
        self,
        user_id: str,
        subject_id: Optional[str] = None,
        graph_version_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Recompiles the subject and cross-subject graphs, persists them to the 'graph_cache'
        table and saves a local disk backup for offline demo resilience (Risk R17).
        """
        # 1. Subject cache
        subject_graph = None
        if subject_id:
            subject_graph = self.assemble_subject_graph(subject_id, user_id)
            cache_key = f"subject:{subject_id}"
            self._save_to_cache(
                cache_key=cache_key,
                user_id=user_id,
                subject_id=subject_id,
                graph_version_id=graph_version_id,
                data=subject_graph,
            )

        # 2. Invalidate / refresh cross-subject cache as well
        cross_graph = self.assemble_cross_subject_graph(user_id)
        cross_cache_key = f"cross_subject:{user_id}"
        self._save_to_cache(
            cache_key=cross_cache_key,
            user_id=user_id,
            subject_id=None,
            graph_version_id=graph_version_id,
            data=cross_graph,
        )

        return subject_graph or cross_graph

    def get_cached_graph(
        self, cache_key: str, user_id: str, subject_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Retrieves graph JSON from the cache table.
        If cache miss occurs, compiles from scratch and caches immediately.
        """
        with get_db_cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT data, updated_at
                FROM graph_cache
                WHERE cache_key = %s AND user_id = %s;
                """,
                (cache_key, user_id),
            )
            row = cursor.fetchone()

        if row and row.get("data"):
            logger.info(f"[GraphService] Cache HIT for key: {cache_key}")
            return row["data"]

        # Cache miss: assemble, cache, and return
        logger.info(f"[GraphService] Cache MISS for key: {cache_key}. Compiling now...")
        if subject_id:
            return self.refresh_and_cache_graph(user_id=user_id, subject_id=subject_id)
        else:
            return self.refresh_and_cache_graph(user_id=user_id)

    def invalidate_cache(self, user_id: str, subject_id: Optional[str] = None) -> None:
        """
        Invalidates cached graph representations for the given subject and user.
        """
        with get_db_cursor() as cursor:
            if subject_id:
                cursor.execute(
                    "DELETE FROM graph_cache WHERE cache_key = %s AND user_id = %s;",
                    (f"subject:{subject_id}", user_id),
                )
            # Always invalidate cross-subject cache
            cursor.execute(
                "DELETE FROM graph_cache WHERE cache_key = %s AND user_id = %s;",
                (f"cross_subject:{user_id}", user_id),
            )
        logger.info(f"[GraphService] Invalidated cache for user {user_id} (subject={subject_id})")

    def _save_to_cache(
        self,
        cache_key: str,
        user_id: str,
        subject_id: Optional[str],
        graph_version_id: Optional[str],
        data: Dict[str, Any],
    ) -> None:
        """
        Persists JSON graph payload to both PostgreSQL 'graph_cache' and local disk.
        """
        data_json = json.dumps(data)

        # 1. Save in PostgreSQL
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO graph_cache (cache_key, user_id, subject_id, graph_version_id, data, updated_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                ON CONFLICT (cache_key)
                DO UPDATE SET
                    graph_version_id = EXCLUDED.graph_version_id,
                    data = EXCLUDED.data,
                    updated_at = NOW();
                """,
                (cache_key, user_id, subject_id, graph_version_id, data_json),
            )

        # 2. Save local disk copy for offline demo support (Risk R17)
        try:
            local_file = self.local_cache_dir / f"{cache_key.replace(':', '_')}.json"
            local_file.write_text(data_json, encoding="utf-8")
        except Exception as e:
            logger.warning(f"[GraphService] Failed to write local cache file: {e}")


graph_service = GraphService()

