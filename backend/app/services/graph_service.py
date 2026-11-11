"""
Graph Compilation, Versioning & Caching Service for StudyGraph.
Relies on:
  - Decision D03: react-force-graph (2D/3D) data structure ({ nodes, links }).
  - Decision D05: PostgreSQL storage with JSONB caching.
  - Decision D12: Local-first cache fallback for offline demo safety (R17).
  - Pipeline Step 12 & 14: Version snapshot creation and graph caching.
"""

from collections import deque
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
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

    def _fetch_evidence_map(self, cursor, edge_ids: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        """Fetches verbatim evidence snippets for edges (Rule 13.1: no evidence, no link)."""
        evidence_by_edge: Dict[str, List[Dict[str, Any]]] = {}
        if not edge_ids:
            return evidence_by_edge
        cursor.execute(
            """
            SELECT edge_id, chunk_id, snippet
            FROM edge_evidence
            WHERE edge_id = ANY(%s::uuid[]);
            """,
            (edge_ids,),
        )
        for ev in cursor.fetchall() or []:
            eid = str(ev["edge_id"])
            evidence_by_edge.setdefault(eid, []).append({
                "chunk_id": str(ev["chunk_id"]) if ev["chunk_id"] else None,
                "snippet": ev["snippet"],
            })
        return evidence_by_edge

    @staticmethod
    def _escape_ilike(term: str) -> str:
        """Escapes SQL LIKE wildcards so literal characters like '%' or '_' search accurately."""
        return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

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

            # 2. Fetch all topics for this subject with cluster labels and merged aliases
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
                    pc.label AS parent_cluster_label,
                    COALESCE(
                        ARRAY_AGG(DISTINCT ta.alias) FILTER (WHERE ta.alias IS NOT NULL),
                        ARRAY[]::text[]
                    ) AS aliases
                FROM topics t
                LEFT JOIN clusters c ON t.cluster_id = c.id
                LEFT JOIN clusters pc ON c.parent_id = pc.id
                LEFT JOIN topic_aliases ta ON ta.topic_id = t.id
                WHERE t.subject_id = %s
                GROUP BY t.id, t.keyword, t.explanation, t.real_world_use, t.module_no, t.reviewed, t.cluster_id, c.label, pc.id, pc.label
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
            evidence_by_edge = self._fetch_evidence_map(cursor, edge_ids)

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
                "aliases": [a for a in (t.get("aliases") or []) if a],
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

            # 2. Fetch all topics across all student subjects (including merged aliases)
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
                    c.label AS cluster_label,
                    COALESCE(
                        ARRAY_AGG(DISTINCT ta.alias) FILTER (WHERE ta.alias IS NOT NULL),
                        ARRAY[]::text[]
                    ) AS aliases
                FROM topics t
                LEFT JOIN clusters c ON t.cluster_id = c.id
                LEFT JOIN topic_aliases ta ON ta.topic_id = t.id
                WHERE t.subject_id = ANY(%s::uuid[])
                GROUP BY t.id, t.subject_id, t.keyword, t.explanation, t.real_world_use, t.module_no, t.reviewed, t.cluster_id, c.label
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
                evidence_by_edge = self._fetch_evidence_map(cursor, edge_ids)

        topic_lookup = {str(t["id"]): t for t in topics}

        nodes = [
            {
                "id": str(t["id"]),
                "name": t["keyword"],
                "keyword": t["keyword"],
                "aliases": [a for a in (t.get("aliases") or []) if a],
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

        links = [
            self._format_edge_payload(e, topic_lookup, subject_map, evidence_by_edge)
            for e in edges
        ]

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

    @staticmethod
    def _format_edge_payload(
        edge: Dict[str, Any],
        topic_lookup: Dict[str, Dict[str, Any]],
        subject_map: Dict[str, str],
        evidence_by_edge: Dict[str, List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        """Formats an edge row consistently for 2D/3D graph renderers and detail drawers."""
        eid = str(edge["id"])
        t_a = topic_lookup.get(str(edge["topic_a"]))
        t_b = topic_lookup.get(str(edge["topic_b"]))

        source_subj_id = str(t_a["subject_id"]) if t_a else ""
        target_subj_id = str(t_b["subject_id"]) if t_b else ""
        source_subj_name = subject_map.get(source_subj_id, "Unknown Subject")
        target_subj_name = subject_map.get(target_subj_id, "Unknown Subject")

        is_cross = (source_subj_id != target_subj_id) or (edge.get("scope") == "cross_subject")
        scope = "cross_subject" if is_cross else "same_subject"
        ev_list = evidence_by_edge.get(eid, [])

        return {
            "id": eid,
            "source": str(edge["topic_a"]),
            "target": str(edge["topic_b"]),
            "source_keyword": t_a["keyword"] if t_a else "Unknown Topic",
            "target_keyword": t_b["keyword"] if t_b else "Unknown Topic",
            "source_subject_id": source_subj_id,
            "target_subject_id": target_subj_id,
            "source_subject_name": source_subj_name,
            "target_subject_name": target_subj_name,
            "type": edge["type"],
            "reason": edge["reason"],
            "industry_example": edge["industry_example"],
            "strength": int(edge["strength"]),
            "scope": scope,
            "status": edge["status"],
            "locked": bool(edge["locked"]),
            "evidence": ev_list,
            "snippet_a": ev_list[0]["snippet"] if len(ev_list) > 0 else None,
            "snippet_b": ev_list[1]["snippet"] if len(ev_list) > 1 else None,
        }

    def search_topics(
        self,
        user_id: str,
        query: str,
        subject_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Searches a student's topics by both canonical keyword and merged topic_aliases.
        Enforces multi-tenant isolation (Rule 11) and ranks exact/prefix matches first.
        """
        cleaned = (query or "").strip()
        if not cleaned:
            return []

        max_results = limit or settings.GRAPH_SEARCH_MAX_SUGGESTIONS
        escaped = self._escape_ilike(cleaned)
        contains_pattern = f"%{escaped}%"
        prefix_pattern = f"{escaped}%"

        subject_clause = "AND t.subject_id = %s" if subject_id else ""
        params: List[Any] = [user_id]
        if subject_id:
            params.append(subject_id)
        params.extend([
            contains_pattern,
            contains_pattern,
            cleaned,
            prefix_pattern,
            cleaned,
            max_results,
        ])

        with get_db_cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(
                f"""
                SELECT
                    t.id,
                    t.subject_id,
                    s.name AS subject_name,
                    t.keyword,
                    t.explanation,
                    t.real_world_use,
                    COALESCE(t.module_no, 1) AS module_no,
                    t.reviewed,
                    c.label AS cluster_label,
                    COALESCE(
                        ARRAY_AGG(DISTINCT ta.alias) FILTER (WHERE ta.alias IS NOT NULL),
                        ARRAY[]::text[]
                    ) AS aliases
                FROM topics t
                JOIN subjects s ON t.subject_id = s.id
                LEFT JOIN clusters c ON t.cluster_id = c.id
                LEFT JOIN topic_aliases ta ON ta.topic_id = t.id
                WHERE s.user_id = %s
                  {subject_clause}
                  AND (
                      t.keyword ILIKE %s ESCAPE '\\'
                      OR EXISTS (
                          SELECT 1
                          FROM topic_aliases ta2
                          WHERE ta2.topic_id = t.id
                            AND ta2.alias ILIKE %s ESCAPE '\\'
                      )
                  )
                GROUP BY t.id, t.subject_id, s.name, t.keyword, t.explanation, t.real_world_use, t.module_no, t.reviewed, c.label
                ORDER BY
                    CASE
                        WHEN LOWER(t.keyword) = LOWER(%s) THEN 0
                        WHEN t.keyword ILIKE %s ESCAPE '\\' THEN 1
                        WHEN EXISTS (
                            SELECT 1 FROM topic_aliases ta3
                            WHERE ta3.topic_id = t.id AND LOWER(ta3.alias) = LOWER(%s)
                        ) THEN 2
                        ELSE 3
                    END,
                    t.keyword ASC
                LIMIT %s;
                """,
                tuple(params),
            )
            rows = cursor.fetchall() or []

        q_lower = cleaned.lower()
        results: List[Dict[str, Any]] = []
        for r in rows:
            aliases = [a for a in (r.get("aliases") or []) if a]
            keyword = r["keyword"]
            matching_aliases = [a for a in aliases if q_lower in a.lower()]
            # Surface the matched alias when the user searched via an alias (or exact alias match)
            matched_alias = matching_aliases[0] if (matching_aliases and q_lower not in keyword.lower()) else (
                matching_aliases[0] if any(a.lower() == q_lower for a in matching_aliases) else None
            )
            results.append({
                "id": str(r["id"]),
                "subject_id": str(r["subject_id"]),
                "subject_name": r["subject_name"],
                "keyword": keyword,
                "aliases": aliases,
                "matched_alias": matched_alias,
                "explanation": r["explanation"],
                "real_world_use": r.get("real_world_use") or "",
                "module_no": int(r.get("module_no") or 1),
                "reviewed": bool(r.get("reviewed")),
                "cluster_label": r.get("cluster_label") or "General",
            })

        return results

    def get_focused_subgraph(
        self,
        topic_id: str,
        user_id: str,
        hops: Optional[int] = None,
        include_weak: bool = False,
        max_nodes: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Builds a localized 1-3 hop neighborhood subgraph around a searched topic
        alongside its Theory Card payload (Feature F13, Risk R09/R14).
        """
        target_hops = hops if hops is not None else settings.GRAPH_SEARCH_DEFAULT_HOPS
        target_hops = max(settings.GRAPH_SEARCH_MIN_HOPS, min(settings.GRAPH_SEARCH_MAX_HOPS, target_hops))
        node_cap = max_nodes if max_nodes is not None else settings.GRAPH_MAX_VISIBLE_NODES
        weak_threshold = settings.GRAPH_WEAK_LINK_THRESHOLD

        with get_db_cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            # 1. Verify topic ownership (Rule 11)
            cursor.execute(
                """
                SELECT t.id, t.subject_id
                FROM topics t
                JOIN subjects s ON t.subject_id = s.id
                WHERE t.id = %s AND s.user_id = %s;
                """,
                (topic_id, user_id),
            )
            center_row = cursor.fetchone()
            if not center_row:
                raise ValueError(f"Topic {topic_id} not found for user {user_id}")

            # 2. Fetch subjects owned by this student
            cursor.execute(
                "SELECT id, name FROM subjects WHERE user_id = %s;",
                (user_id,),
            )
            subject_map = {str(s["id"]): s["name"] for s in (cursor.fetchall() or [])}

            # 3. Fetch all active edges owned by this student so hops span same + cross-subject links
            cursor.execute(
                """
                SELECT
                    e.id, e.topic_a, e.topic_b, e.type, e.reason, e.industry_example,
                    e.strength, e.scope, e.status, e.locked, e.graph_version
                FROM edges e
                JOIN topics ta ON e.topic_a = ta.id
                JOIN subjects sa ON ta.subject_id = sa.id
                JOIN topics tb ON e.topic_b = tb.id
                JOIN subjects sb ON tb.subject_id = sb.id
                WHERE e.status != 'deleted'
                  AND sa.user_id = %s
                  AND sb.user_id = %s
                ORDER BY e.strength DESC;
                """,
                (user_id, user_id),
            )
            all_edges = cursor.fetchall() or []

            # Build adjacency for BFS using visible links (or all active links when include_weak=True)
            adjacency: Dict[str, List[Tuple[str, int]]] = {}
            for e in all_edges:
                strength = int(e.get("strength") or 1)
                if not include_weak and strength < weak_threshold:
                    continue
                a_id = str(e["topic_a"])
                b_id = str(e["topic_b"])
                adjacency.setdefault(a_id, []).append((b_id, strength))
                adjacency.setdefault(b_id, []).append((a_id, strength))

            # BFS prioritizing stronger links when node_cap limits expansion
            hop_map: Dict[str, int] = {topic_id: 0}
            queue: deque[Tuple[str, int]] = deque([(topic_id, 0)])
            while queue:
                curr_id, dist = queue.popleft()
                if dist >= target_hops:
                    continue
                neighbors = sorted(adjacency.get(curr_id, []), key=lambda item: item[1], reverse=True)
                for nbr_id, _ in neighbors:
                    if nbr_id in hop_map:
                        continue
                    if len(hop_map) >= node_cap:
                        break
                    hop_map[nbr_id] = dist + 1
                    queue.append((nbr_id, dist + 1))

            # Filter edges within the discovered neighborhood
            included_ids = set(hop_map.keys())
            neighborhood_edges = [
                e for e in all_edges
                if str(e["topic_a"]) in included_ids and str(e["topic_b"]) in included_ids
            ]

            hidden_weak_count = 0
            if not include_weak:
                # Count weak links attached to the focus node or within the neighborhood
                hidden_weak_edges = [
                    e for e in all_edges
                    if int(e.get("strength") or 1) < weak_threshold
                    and (
                        (str(e["topic_a"]) in included_ids and str(e["topic_b"]) in included_ids)
                        or str(e["topic_a"]) == topic_id
                        or str(e["topic_b"]) == topic_id
                    )
                ]
                hidden_weak_count = len(hidden_weak_edges)
                visible_edges = [
                    e for e in neighborhood_edges
                    if int(e.get("strength") or 1) >= weak_threshold
                ]
            else:
                visible_edges = neighborhood_edges

            # 4. Fetch full details + aliases for the discovered neighborhood nodes
            node_ids = list(hop_map.keys())
            cursor.execute(
                """
                SELECT
                    t.id,
                    t.subject_id,
                    t.keyword,
                    t.explanation,
                    t.real_world_use,
                    COALESCE(t.module_no, 1) AS module_no,
                    t.reviewed,
                    t.cluster_id,
                    c.label AS cluster_label,
                    pc.label AS parent_cluster_label,
                    COALESCE(
                        ARRAY_AGG(DISTINCT ta.alias) FILTER (WHERE ta.alias IS NOT NULL),
                        ARRAY[]::text[]
                    ) AS aliases
                FROM topics t
                LEFT JOIN clusters c ON t.cluster_id = c.id
                LEFT JOIN clusters pc ON c.parent_id = pc.id
                LEFT JOIN topic_aliases ta ON ta.topic_id = t.id
                WHERE t.id = ANY(%s::uuid[])
                GROUP BY t.id, t.subject_id, t.keyword, t.explanation, t.real_world_use, t.module_no, t.reviewed, t.cluster_id, c.label, pc.label;
                """,
                (node_ids,),
            )
            topic_rows = cursor.fetchall() or []

            # 5. Fetch verbatim evidence snippets for visible links
            visible_edge_ids = [str(e["id"]) for e in visible_edges]
            evidence_by_edge = self._fetch_evidence_map(cursor, visible_edge_ids)

        topic_lookup = {str(t["id"]): t for t in topic_rows}
        nodes = []
        for t in sorted(topic_rows, key=lambda r: (hop_map.get(str(r["id"]), 99), r["keyword"])):
            tid = str(t["id"])
            sid = str(t["subject_id"])
            nodes.append({
                "id": tid,
                "name": t["keyword"],
                "keyword": t["keyword"],
                "aliases": [a for a in (t.get("aliases") or []) if a],
                "explanation": t["explanation"],
                "real_world_use": t.get("real_world_use") or "",
                "module_no": int(t.get("module_no") or 1),
                "reviewed": bool(t.get("reviewed")),
                "cluster_id": str(t["cluster_id"]) if t.get("cluster_id") else None,
                "cluster_label": t.get("cluster_label") or "General",
                "parent_cluster_label": t.get("parent_cluster_label") or t.get("cluster_label") or "Core",
                "subject_id": sid,
                "subject_name": subject_map.get(sid, "Subject"),
                "hop_distance": hop_map.get(tid, 0),
                "is_focus": tid == topic_id,
            })

        links = [
            self._format_edge_payload(e, topic_lookup, subject_map, evidence_by_edge)
            for e in visible_edges
        ]

        focus_node = next((n for n in nodes if n["id"] == topic_id), None)

        return {
            "scope": "focused",
            "hops": target_hops,
            "focus_topic": focus_node,
            "subjects": [
                {"id": sid, "name": subject_map[sid]}
                for sid in sorted({n["subject_id"] for n in nodes}, key=lambda s: subject_map.get(s, ""))
            ],
            "nodes": nodes,
            "links": links,
            "stats": {
                "hops": target_hops,
                "node_count": len(nodes),
                "link_count": len(links),
                "hidden_weak_count": hidden_weak_count,
                "cross_subject_links": sum(1 for l in links if l["scope"] == "cross_subject"),
            },
        }


graph_service = GraphService()

