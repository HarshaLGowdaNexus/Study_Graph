"""
Louvain Community Detection & Hierarchical Clustering Service for StudyGraph.
Relies on:
  - Decision D11: NetworkX Louvain Community Detection.
  - Quality Gate R09: Prevent graph hairball through a two-tier hierarchy (Cluster -> Sub-cluster -> Topics).
"""

import logging
from typing import Any, Dict, List, Optional, Set, Tuple
import networkx as nx
import psycopg2.extras

from backend.app.database import get_db_cursor

logger = logging.getLogger(__name__)


class ClusterService:
    """
    Groups subject topics into a clean two-tier hierarchy (Clusters & Sub-clusters)
    using NetworkX Louvain Community Detection weighted by verified edge strength.
    """

    def build_subject_clusters(self, subject_id: str) -> Dict[str, Any]:
        """
        Executes Louvain community detection for all active topics and verified edges
        within the given subject folder, updates the 'clusters' and 'topics' tables,
        and returns the resulting cluster hierarchy.
        """
        logger.info(f"[ClusterService] Starting community detection for subject {subject_id}")

        with get_db_cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            # 1. Fetch all topics for this subject
            cursor.execute(
                """
                SELECT id, keyword, module_no
                FROM topics
                WHERE subject_id = %s
                ORDER BY keyword ASC;
                """,
                (subject_id,),
            )
            topics = cursor.fetchall()

            if not topics:
                logger.info(f"[ClusterService] No topics found for subject {subject_id}. Skipping.")
                return {"clusters": [], "total_topics": 0, "total_clusters": 0}

            topic_map = {str(t["id"]): t["keyword"] for t in topics}
            topic_ids = list(topic_map.keys())

            # 2. Fetch all verified intra-subject edges (status != 'deleted')
            cursor.execute(
                """
                SELECT topic_a, topic_b, strength
                FROM edges
                WHERE status != 'deleted'
                  AND scope = 'same_subject'
                  AND topic_a = ANY(%s::uuid[])
                  AND topic_b = ANY(%s::uuid[]);
                """,
                (topic_ids, topic_ids),
            )
            edges = cursor.fetchall()

        # 3. Build NetworkX undirected graph
        G = nx.Graph()
        for tid, keyword in topic_map.items():
            G.add_node(tid, keyword=keyword)

        for edge in edges:
            u = str(edge["topic_a"])
            v = str(edge["topic_b"])
            weight = int(edge.get("strength") or 1)
            if G.has_node(u) and G.has_node(v) and u != v:
                G.add_edge(u, v, weight=weight)

        # 4. Partition topics into hierarchical communities
        hierarchy = self._compute_louvain_hierarchy(G, topic_map)

        # 5. Persist clusters and update topics in database
        persisted_summary = self._persist_clusters(subject_id, hierarchy)

        logger.info(
            f"[ClusterService] Successfully clustered subject {subject_id}: "
            f"{persisted_summary['top_level_count']} top-level clusters, "
            f"{persisted_summary['sub_cluster_count']} sub-clusters across {len(topic_ids)} topics."
        )

        return persisted_summary

    def _compute_louvain_hierarchy(
        self, G: nx.Graph, topic_map: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        """
        Computes 2-tier hierarchy (Cluster -> Sub-clusters -> Topics) using Louvain algorithm.
        """
        all_nodes = set(G.nodes())
        if not all_nodes:
            return []

        # Find connected components to handle isolated topics cleanly
        components = list(nx.connected_components(G))
        isolated_nodes: Set[str] = set()
        connected_subgraphs: List[nx.Graph] = []

        for comp in components:
            if len(comp) == 1:
                isolated_nodes.update(comp)
            else:
                connected_subgraphs.append(G.subgraph(comp).copy())

        hierarchy: List[Dict[str, Any]] = []

        # Process connected components with Louvain
        for sub_g in connected_subgraphs:
            try:
                # Use louvain_partitions for natural hierarchical aggregation
                partitions = list(nx.community.louvain_partitions(sub_g, weight="weight"))
            except Exception as e:
                logger.warning(f"[ClusterService] Louvain partition error: {e}. Falling back to single community.")
                partitions = [[set(sub_g.nodes())]]

            if len(partitions) >= 2:
                # Coarser partition is top-level cluster; finer is sub-clusters
                coarse_communities = partitions[-1]
                fine_communities = partitions[0]

                for coarse_comm in coarse_communities:
                    cluster_nodes = set(coarse_comm)
                    cluster_label = self._select_central_label(sub_g, cluster_nodes, topic_map)

                    # Find fine sub-communities that belong to this coarse community
                    sub_clusters: List[Dict[str, Any]] = []
                    for fine_comm in fine_communities:
                        overlap = fine_comm.intersection(cluster_nodes)
                        if overlap:
                            sub_label = self._select_central_label(sub_g, overlap, topic_map)
                            sub_clusters.append({
                                "label": sub_label,
                                "topics": list(overlap),
                            })

                    hierarchy.append({
                        "label": cluster_label,
                        "sub_clusters": sub_clusters,
                        "all_topics": list(cluster_nodes),
                    })

            else:
                # Only 1 partition returned by Louvain
                communities = partitions[0] if partitions else [set(sub_g.nodes())]
                for comm in communities:
                    comm_nodes = set(comm)
                    cluster_label = self._select_central_label(sub_g, comm_nodes, topic_map)

                    # If community is large (>= 4 nodes), attempt fine Louvain with higher resolution
                    if len(comm_nodes) >= 4:
                        try:
                            fine_g = sub_g.subgraph(comm_nodes)
                            fine_comms = list(nx.community.louvain_communities(fine_g, weight="weight", resolution=1.5))
                        except Exception:
                            fine_comms = [comm_nodes]
                    else:
                        fine_comms = [comm_nodes]

                    sub_clusters = []
                    for fc in fine_comms:
                        sub_label = self._select_central_label(sub_g, set(fc), topic_map)
                        sub_clusters.append({
                            "label": sub_label,
                            "topics": list(fc),
                        })

                    hierarchy.append({
                        "label": cluster_label,
                        "sub_clusters": sub_clusters,
                        "all_topics": list(comm_nodes),
                    })

        # Process isolated/unlinked topics
        if isolated_nodes:
            # Group isolated nodes into an unlinked topics cluster
            unlinked_topics = list(isolated_nodes)
            hierarchy.append({
                "label": "Foundations & Unlinked Concepts",
                "sub_clusters": [
                    {
                        "label": f"Module {topic_map.get(tid, 'Topic')[:25]}",
                        "topics": [tid],
                    }
                    for tid in unlinked_topics
                ],
                "all_topics": unlinked_topics,
            })

        return hierarchy

    def _select_central_label(
        self, G: nx.Graph, nodes: Set[str], topic_map: Dict[str, str]
    ) -> str:
        """
        Determines the most central, representative topic in a community to serve as its label.
        Uses highest weighted degree inside the community; falls back to first keyword.
        """
        if not nodes:
            return "General Cluster"

        if len(nodes) == 1:
            node_id = next(iter(nodes))
            return topic_map.get(node_id, "Core Concept")

        sub_g = G.subgraph(nodes)
        best_node = None
        best_degree = -1.0

        for n in nodes:
            deg = sub_g.degree(n, weight="weight")
            if deg > best_degree:
                best_degree = deg
                best_node = n

        if best_node and best_node in topic_map:
            return topic_map[best_node]

        first_node = next(iter(nodes))
        return topic_map.get(first_node, "Core Concept")

    def _persist_clusters(
        self, subject_id: str, hierarchy: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Writes cluster and sub-cluster records to the database and updates topics.cluster_id.
        """
        with get_db_cursor() as cursor:
            # Clear old clusters for this subject (topics.cluster_id set null automatically by FK)
            cursor.execute("UPDATE topics SET cluster_id = NULL WHERE subject_id = %s;", (subject_id,))
            cursor.execute("DELETE FROM clusters WHERE subject_id = %s;", (subject_id,))

            top_level_count = 0
            sub_cluster_count = 0
            created_clusters: List[Dict[str, Any]] = []

            for cluster_info in hierarchy:
                # 1. Insert Top-level cluster (parent_id = NULL)
                cursor.execute(
                    """
                    INSERT INTO clusters (subject_id, parent_id, label)
                    VALUES (%s, NULL, %s)
                    RETURNING id;
                    """,
                    (subject_id, cluster_info["label"]),
                )
                parent_cluster_id = str(cursor.fetchone()[0])
                top_level_count += 1

                sub_list = []
                for sub_info in cluster_info["sub_clusters"]:
                    # 2. Insert Sub-cluster (parent_id = parent_cluster_id)
                    cursor.execute(
                        """
                        INSERT INTO clusters (subject_id, parent_id, label)
                        VALUES (%s, %s, %s)
                        RETURNING id;
                        """,
                        (subject_id, parent_cluster_id, sub_info["label"]),
                    )
                    sub_cluster_id = str(cursor.fetchone()[0])
                    sub_cluster_count += 1

                    # 3. Associate topics with the sub-cluster
                    sub_topics = sub_info.get("topics", [])
                    if sub_topics:
                        cursor.execute(
                            """
                            UPDATE topics
                            SET cluster_id = %s
                            WHERE id = ANY(%s::uuid[]);
                            """,
                            (sub_cluster_id, sub_topics),
                        )

                    sub_list.append({
                        "id": sub_cluster_id,
                        "label": sub_info["label"],
                        "topic_ids": sub_topics,
                    })

                created_clusters.append({
                    "id": parent_cluster_id,
                    "label": cluster_info["label"],
                    "sub_clusters": sub_list,
                })

        return {
            "subject_id": subject_id,
            "top_level_count": top_level_count,
            "sub_cluster_count": sub_cluster_count,
            "clusters": created_clusters,
        }


cluster_service = ClusterService()

