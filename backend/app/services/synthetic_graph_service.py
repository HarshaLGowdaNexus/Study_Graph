"""
Synthetic Benchmark Graph Service for StudyGraph (Task T14).
Generates realistic, deterministic 500-topic graphs to stress-test rendering smoothness,
force-directed layout stability, and clustering readability without database overhead.

Relies on:
  - Feature F11: Subject graph: clusters, click to zoom into sub-graph
  - Risks R09 & R14: Graph hairball prevention and FPS lag benchmarks
  - Quality Gate G08: Rendering responsiveness with large graphs
"""

import random
from typing import Any, Dict, List, Optional


class SyntheticGraphService:
    """
    Creates deterministic synthetic knowledge graphs with clustered topology,
    varied link strengths (1-5), and evidence snippets for stress-testing.
    """

    CLUSTER_SPECS = [
        {
            "id": "syn-cluster-1",
            "label": "Network Architectures & Reference Models",
            "sub_clusters": [
                {"id": "syn-sub-1a", "label": "OSI 7-Layer Model"},
                {"id": "syn-sub-1b", "label": "TCP/IP Protocol Suite"},
                {"id": "syn-sub-1c", "label": "Packet vs Circuit Switching"},
            ],
            "prefix": "Arch",
        },
        {
            "id": "syn-cluster-2",
            "label": "Transport Layer & Flow Control",
            "sub_clusters": [
                {"id": "syn-sub-2a", "label": "TCP Connection Lifecycle"},
                {"id": "syn-sub-2b", "label": "Sliding Window & Flow Control"},
                {"id": "syn-sub-2c", "label": "Congestion Control Algorithms"},
            ],
            "prefix": "Transport",
        },
        {
            "id": "syn-cluster-3",
            "label": "Routing Protocols & IP Addressing",
            "sub_clusters": [
                {"id": "syn-sub-3a", "label": "Distance Vector & Link State"},
                {"id": "syn-sub-3b", "label": "BGP & Autonomous Systems"},
                {"id": "syn-sub-3c", "label": "IPv4 Subnetting & CIDR"},
            ],
            "prefix": "Routing",
        },
        {
            "id": "syn-cluster-4",
            "label": "Data Link Layer & MAC Protocols",
            "sub_clusters": [
                {"id": "syn-sub-4a", "label": "Ethernet & CSMA/CD"},
                {"id": "syn-sub-4b", "label": "Error Detection & CRC"},
                {"id": "syn-sub-4c", "label": "VLANs & Spanning Tree"},
            ],
            "prefix": "DataLink",
        },
        {
            "id": "syn-cluster-5",
            "label": "Application Layer & Web Systems",
            "sub_clusters": [
                {"id": "syn-sub-5a", "label": "HTTP/1.1, HTTP/2 & HTTP/3"},
                {"id": "syn-sub-5b", "label": "DNS Resolution Hierarchy"},
                {"id": "syn-sub-5c", "label": "TLS Handshake & Certificates"},
            ],
            "prefix": "AppLayer",
        },
        {
            "id": "syn-cluster-6",
            "label": "Network Security & Cryptography",
            "sub_clusters": [
                {"id": "syn-sub-6a", "label": "Symmetric & Asymmetric Ciphers"},
                {"id": "syn-sub-6b", "label": "Firewalls & Packet Filters"},
                {"id": "syn-sub-6c", "label": "IPsec & VPN Tunneling"},
            ],
            "prefix": "Security",
        },
        {
            "id": "syn-cluster-7",
            "label": "Wireless, Mobile & Cellular Networks",
            "sub_clusters": [
                {"id": "syn-sub-7a", "label": "Wi-Fi (802.11 a/b/g/n/ac/ax)"},
                {"id": "syn-sub-7b", "label": "Cellular Handoff (4G LTE / 5G)"},
                {"id": "syn-sub-7c", "label": "CSMA/CA & Hidden Terminal"},
            ],
            "prefix": "Wireless",
        },
        {
            "id": "syn-cluster-8",
            "label": "Cloud Infrastructure & Distributed CDN",
            "sub_clusters": [
                {"id": "syn-sub-8a", "label": "Load Balancing & Reverse Proxies"},
                {"id": "syn-sub-8b", "label": "Edge Caching & Anycast DNS"},
                {"id": "syn-sub-8c", "label": "Software-Defined Networking (SDN)"},
            ],
            "prefix": "Cloud",
        },
    ]

    LINK_TYPES = [
        "prerequisite_of",
        "applies_in",
        "part_of",
        "contrasts_with",
        "same_concept",
        "example_of",
    ]

    def generate_benchmark_graph(
        self,
        node_count: int = 500,
        cluster_filter: Optional[str] = None,
        max_visible_nodes: Optional[int] = None,
        seed: int = 42,
    ) -> Dict[str, Any]:
        """
        Generates a synthetic clustered graph with exactly `node_count` nodes
        and realistic edge distribution (average node degree ~3.5 to 4.5).
        """
        rng = random.Random(seed)
        num_clusters = len(self.CLUSTER_SPECS)
        base_per_cluster = node_count // num_clusters
        remainder = node_count % num_clusters

        nodes: List[Dict[str, Any]] = []
        cluster_nodes_map: Dict[str, List[str]] = {c["id"]: [] for c in self.CLUSTER_SPECS}

        topic_counter = 1
        for i, cluster in enumerate(self.CLUSTER_SPECS):
            cluster_size = base_per_cluster + (1 if i < remainder else 0)
            subs = cluster["sub_clusters"]

            for j in range(cluster_size):
                sub = subs[j % len(subs)]
                topic_id = f"syn-topic-{topic_counter:04d}"
                keyword = f"{cluster['prefix']} Topic #{topic_counter}: {sub['label']} Unit {j+1}"
                
                module_no = (i % 5) + 1
                reviewed = rng.random() > 0.15  # 85% reviewed

                nodes.append({
                    "id": topic_id,
                    "name": keyword,
                    "keyword": keyword,
                    "explanation": (
                        f"Fundamental concept in {cluster['label']}.\n"
                        f"Governs {sub['label']} operational behavior across distributed nodes.\n"
                        f"Ensures deterministic throughput and low latency under high packet loads.\n"
                        f"Forms a core syllabus topic in Module {module_no}."
                    ),
                    "real_world_use": f"Deployed in high-performance production systems and cloud data centers for {cluster['label'].lower()}.",
                    "module_no": module_no,
                    "reviewed": reviewed,
                    "cluster_id": sub["id"],
                    "cluster_label": sub["label"],
                    "parent_cluster_id": cluster["id"],
                    "parent_cluster_label": cluster["label"],
                    "subject_id": "synthetic-stress-test",
                    "subject_name": "Computer Networks (500-Topic Stress Test)",
                })

                cluster_nodes_map[cluster["id"]].append(topic_id)
                topic_counter += 1

        # Generate realistic clustered links
        # ~80% of links are intra-cluster (tight communities), ~20% are inter-cluster bridges
        links: List[Dict[str, Any]] = []
        edge_set = set()
        edge_counter = 1

        # 1. Intra-cluster links (each node links to 2-4 peers in the same cluster)
        for cluster in self.CLUSTER_SPECS:
            c_nodes = cluster_nodes_map[cluster["id"]]
            n_c = len(c_nodes)
            for src_idx, src_id in enumerate(c_nodes):
                # Connect to immediate neighbor (creates connected path)
                next_idx = (src_idx + 1) % n_c
                dst_id = c_nodes[next_idx]
                pair = tuple(sorted([src_id, dst_id]))
                if pair not in edge_set:
                    edge_set.add(pair)
                    strength = rng.randint(2, 5)
                    ltype = rng.choice(self.LINK_TYPES)
                    links.append({
                        "id": f"syn-edge-{edge_counter:05d}",
                        "source": src_id,
                        "target": dst_id,
                        "type": ltype,
                        "reason": f"{src_id} directly establishes protocol preconditions for {dst_id} in {cluster['label']}.",
                        "industry_example": f"Applied during packet transmission pipelines in enterprise routers and switches.",
                        "strength": strength,
                        "scope": "same_subject",
                        "status": "accepted",
                        "locked": rng.random() < 0.05,
                        "graph_version": 1,
                        "evidence": [
                            {
                                "chunk_id": f"syn-chunk-{rng.randint(100, 999)}",
                                "snippet": f"The standard specification dictates that {cluster['label']} modules enforce strict synchronization between endpoints.",
                            },
                            {
                                "chunk_id": f"syn-chunk-{rng.randint(100, 999)}",
                                "snippet": f"Empirical network telemetry indicates throughput drops without coordinated flow control mechanisms.",
                            },
                        ],
                    })
                    edge_counter += 1

                # Add 1-2 random internal hops
                for _ in range(rng.randint(1, 2)):
                    rand_target = rng.choice(c_nodes)
                    if rand_target != src_id:
                        r_pair = tuple(sorted([src_id, rand_target]))
                        if r_pair not in edge_set:
                            edge_set.add(r_pair)
                            links.append({
                                "id": f"syn-edge-{edge_counter:05d}",
                                "source": src_id,
                                "target": rand_target,
                                "type": rng.choice(self.LINK_TYPES),
                                "reason": f"Shared functional dependency within {cluster['label']}.",
                                "industry_example": "Used in cloud hypervisors and load balancers.",
                                "strength": rng.randint(1, 5),
                                "scope": "same_subject",
                                "status": "accepted",
                                "locked": False,
                                "graph_version": 1,
                                "evidence": [
                                    {
                                        "chunk_id": f"syn-chunk-{rng.randint(100, 999)}",
                                        "snippet": "Network nodes share operational state tables to synchronize packet buffers.",
                                    }
                                ],
                            })
                            edge_counter += 1

        # 2. Inter-cluster bridging links (~10-15 links between adjacent clusters)
        for i in range(num_clusters):
            c_src = self.CLUSTER_SPECS[i]["id"]
            c_dst = self.CLUSTER_SPECS[(i + 1) % num_clusters]["id"]
            src_candidates = cluster_nodes_map[c_src]
            dst_candidates = cluster_nodes_map[c_dst]

            for _ in range(rng.randint(12, 18)):
                src_id = rng.choice(src_candidates)
                dst_id = rng.choice(dst_candidates)
                b_pair = tuple(sorted([src_id, dst_id]))
                if b_pair not in edge_set:
                    edge_set.add(b_pair)
                    links.append({
                        "id": f"syn-edge-{edge_counter:05d}",
                        "source": src_id,
                        "target": dst_id,
                        "type": "applies_in",
                        "reason": f"Cross-layer architectural linkage between {self.CLUSTER_SPECS[i]['label']} and {self.CLUSTER_SPECS[(i+1)%num_clusters]['label']}.",
                        "industry_example": "Critical cross-layer optimization used in streaming and modern microservice fabrics.",
                        "strength": rng.randint(1, 4),
                        "scope": "same_subject",
                        "status": "accepted",
                        "locked": False,
                        "graph_version": 1,
                        "evidence": [
                            {
                                "chunk_id": f"syn-chunk-{rng.randint(100, 999)}",
                                "snippet": "Higher layer protocols adapt transmission windows based on physical and link layer error feedback.",
                            }
                        ],
                    })
                    edge_counter += 1

        # Apply cluster filter if requested (zoom into sub-graph)
        filtered_nodes = nodes
        if cluster_filter:
            filtered_nodes = [
                n for n in nodes
                if n.get("parent_cluster_id") == cluster_filter or n.get("cluster_id") == cluster_filter
            ]
            valid_ids = {n["id"] for n in filtered_nodes}
            links = [l for l in links if l["source"] in valid_ids and l["target"] in valid_ids]

        # Apply max visible node cap if specified
        total_available = len(filtered_nodes)
        if max_visible_nodes and max_visible_nodes < total_available:
            # Keep top nodes by degree to preserve network structure
            degree_map: Dict[str, int] = {}
            for l in links:
                degree_map[l["source"]] = degree_map.get(l["source"], 0) + 1
                degree_map[l["target"]] = degree_map.get(l["target"], 0) + 1
            
            sorted_nodes = sorted(
                filtered_nodes,
                key=lambda n: degree_map.get(n["id"], 0),
                reverse=True
            )
            filtered_nodes = sorted_nodes[:max_visible_nodes]
            active_ids = {n["id"] for n in filtered_nodes}
            links = [l for l in links if l["source"] in active_ids and l["target"] in active_ids]

        clusters_tree = [
            {
                "id": c["id"],
                "label": c["label"],
                "sub_clusters": c["sub_clusters"],
            }
            for c in self.CLUSTER_SPECS
        ]

        return {
            "subject_id": "synthetic-stress-test",
            "subject_name": "Computer Networks (500-Topic Stress Test)",
            "scope": "synthetic",
            "nodes": filtered_nodes,
            "links": links,
            "clusters": clusters_tree,
            "stats": {
                "node_count": len(filtered_nodes),
                "total_available_nodes": total_available,
                "link_count": len(links),
                "cluster_count": len(clusters_tree),
                "is_synthetic": True,
            },
        }


synthetic_graph_service = SyntheticGraphService()

