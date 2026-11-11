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

    def generate_cross_subject_benchmark(self) -> Dict[str, Any]:
        """
        Generates a rich, multi-subject benchmark graph with genuine cross-subject links
        for 3D testing, demo rehearsals (R17, G09, G10), and offline resilience (D12).
        Covers 4 core CS subjects:
          1. Computer Networks (CN)
          2. Operating Systems (OS)
          3. Database Management Systems (DBMS)
          4. Computer Architecture (CA)
        """
        subjects = [
            {"id": "subj-networks", "name": "Computer Networks", "center": {"x": -180, "y": 70, "z": -40}},
            {"id": "subj-os", "name": "Operating Systems", "center": {"x": 180, "y": 70, "z": -40}},
            {"id": "subj-dbms", "name": "Database Management Systems", "center": {"x": -130, "y": -110, "z": 40}},
            {"id": "subj-arch", "name": "Computer Architecture", "center": {"x": 130, "y": -110, "z": 40}},
        ]

        subject_centers = {s["id"]: s["center"] for s in subjects}

        subject_nodes = {
            "subj-networks": [
                {"id": "t-cn-1", "keyword": "Socket Programming", "explanation": "API facilitating bi-directional network communication channels between processes over IP networks.", "real_world_use": "Powers backend web servers, chat servers, and microservice RPC communication."},
                {"id": "t-cn-2", "keyword": "TCP Flow Control", "explanation": "Sliding window protocol preventing a fast sender from overwhelming a slow receiver's buffer.", "real_world_use": "Guarantees reliable video streaming and file transfers over variable speed connections."},
                {"id": "t-cn-3", "keyword": "Packet Encapsulation", "explanation": "Wrapping higher-layer data payloads with protocol headers at each OSI layer.", "real_world_use": "Enables heterogeneous internet routers to forward payloads without inspecting contents."},
                {"id": "t-cn-4", "keyword": "DNS Resolution", "explanation": "Hierarchical distributed database translating human domain names to numerical IP addresses.", "real_world_use": "Every web browser navigation begins with a recursive DNS lookup query."},
                {"id": "t-cn-5", "keyword": "BGP Routing", "explanation": "Path-vector exterior gateway protocol coordinating packet routes across autonomous systems.", "real_world_use": "Forms the global backbone routing table linking ISPs worldwide."},
            ],
            "subj-os": [
                {"id": "t-os-1", "keyword": "System Calls", "explanation": "Programmatic interface allowing user programs to request privileged kernel services.", "real_world_use": "Every file read, process fork, and network transmit requires invoking a system call."},
                {"id": "t-os-2", "keyword": "Virtual Memory & Paging", "explanation": "Memory management mapping virtual addresses to physical frames with secondary swap.", "real_world_use": "Allows machines to execute programs larger than available physical RAM."},
                {"id": "t-os-3", "keyword": "Mutex & Semaphore", "explanation": "Synchronization primitives preventing concurrent race conditions in shared critical sections.", "real_world_use": "Coordinates thread safety in multi-threaded browser engines and databases."},
                {"id": "t-os-4", "keyword": "Process Scheduling", "explanation": "Kernel algorithm allocating CPU time slices among runnable execution threads.", "real_world_use": "Linux CFS scheduler balances interactive GUI latency with background compute throughput."},
                {"id": "t-os-5", "keyword": "File System Inodes", "explanation": "Data structure storing metadata, permissions, and disk block pointers for filesystem objects.", "real_world_use": "Underlies POSIX filesystems like ext4 in Android and Linux servers."},
            ],
            "subj-dbms": [
                {"id": "t-dbms-1", "keyword": "Buffer Pool Management", "explanation": "In-memory cache manager maintaining fixed-size disk frame pages with LRU eviction.", "real_world_use": "Ensures database engines avoid disk I/O on frequently accessed table pages."},
                {"id": "t-dbms-2", "keyword": "Two-Phase Locking (2PL)", "explanation": "Concurrency protocol guaranteeing serializability via expanding and shrinking lock phases.", "real_world_use": "Enforces strict ACID transaction isolation in financial banking databases."},
                {"id": "t-dbms-3", "keyword": "B+ Tree Indexing", "explanation": "Balanced N-ary search tree optimized for disk block reads and high-speed range queries.", "real_world_use": "Default primary and secondary index storage engine in MySQL and PostgreSQL."},
                {"id": "t-dbms-4", "keyword": "Write-Ahead Logging (WAL)", "explanation": "Durability mechanism logging data modifications to append-only disk before applying to tables.", "real_world_use": "Guarantees crash recovery without losing committed financial transactions."},
                {"id": "t-dbms-5", "keyword": "Query Optimization", "explanation": "Cost-based optimizer selecting optimal relational join algorithms and index paths.", "real_world_use": "Transforms declarative SQL queries into low-latency execution plans."},
            ],
            "subj-arch": [
                {"id": "t-arch-1", "keyword": "CPU Cache Hierarchy", "explanation": "Multi-tier SRAM memory (L1/L2/L3) caching instructions and data close to processor cores.", "real_world_use": "Reduces CPU memory latency from 100ns (DRAM) to sub-nanosecond L1 speeds."},
                {"id": "t-arch-2", "keyword": "Direct Memory Access (DMA)", "explanation": "Hardware subsystem enabling I/O devices to transfer data directly to RAM without CPU overhead.", "real_world_use": "High-throughput NVMe drives and 100Gbps network cards stream directly to host memory."},
                {"id": "t-arch-3", "keyword": "Instruction Pipelining", "explanation": "Instruction-level parallelism breaking instruction execution into staggered overlapping stages.", "real_world_use": "Dramatically boosts CPU throughput in modern x86 and ARM processors."},
                {"id": "t-arch-4", "keyword": "Interrupt Handling", "explanation": "Hardware signal diverting CPU execution to dedicated Interrupt Service Routines (ISRs).", "real_world_use": "Enables asynchronous hardware notifications from keyboard, mouse, and network devices."},
                {"id": "t-arch-5", "keyword": "Memory Management Unit (MMU)", "explanation": "Hardware component translating virtual addresses to physical addresses using page tables and TLB.", "real_world_use": "Hardware anchor enforcing memory protection and process isolation across operating systems."},
            ],
        }

        all_nodes = []
        subj_name_map = {s["id"]: s["name"] for s in subjects}

        for sid, t_list in subject_nodes.items():
            center = subject_centers.get(sid, {"x": 0.0, "y": 0.0, "z": 0.0})
            for i, t in enumerate(t_list):
                # Spread nodes around subject galaxy center for clear visual separation
                angle = (i / len(t_list)) * 2 * 3.14159
                radius = 40.0
                node_x = center["x"] + radius * (0.8 if i % 2 == 0 else 1.2) * (1 if i % 3 == 0 else -0.7)
                node_y = center["y"] + radius * (0.9 if i % 2 != 0 else -1.1)
                node_z = center["z"] + ((i - 2) * 16.0)

                all_nodes.append({
                    "id": t["id"],
                    "name": t["keyword"],
                    "keyword": t["keyword"],
                    "explanation": t["explanation"],
                    "real_world_use": t["real_world_use"],
                    "module_no": 1,
                    "reviewed": True,
                    "cluster_label": subj_name_map[sid],
                    "subject_id": sid,
                    "subject_name": subj_name_map[sid],
                    "x": node_x,
                    "y": node_y,
                    "z": node_z,
                })

        # Cross-Subject links covering full 1-5 strength spectrum
        cross_links = [
            # Strength 5: Foundational dependencies
            {
                "id": "cross-link-1",
                "source": "t-cn-1",
                "target": "t-os-1",
                "source_keyword": "Socket Programming",
                "target_keyword": "System Calls",
                "source_subject_id": "subj-networks",
                "target_subject_id": "subj-os",
                "source_subject_name": "Computer Networks",
                "target_subject_name": "Operating Systems",
                "type": "applies_in",
                "strength": 5,
                "scope": "cross_subject",
                "reason": "Network socket APIs (socket, bind, listen, accept) invoke kernel system calls to transfer network packets through device drivers.",
                "industry_example": "Nginx web servers make non-blocking epoll system calls to accept high volumes of incoming TCP network connections.",
                "status": "approved",
                "locked": True,
                "evidence": [
                    {"snippet": "Socket programming relies on OS abstraction layers to read and write bytes over transport layer TCP connections."},
                    {"snippet": "System calls bridge user space applications to kernel-space network protocol stacks and device drivers."},
                ],
                "snippet_a": "Socket programming relies on OS abstraction layers to read and write bytes over transport layer TCP connections.",
                "snippet_b": "System calls bridge user space applications to kernel-space network protocol stacks and device drivers.",
            },
            {
                "id": "cross-link-8",
                "source": "t-arch-5",
                "target": "t-os-2",
                "source_keyword": "Memory Management Unit (MMU)",
                "target_keyword": "Virtual Memory & Paging",
                "source_subject_id": "subj-arch",
                "target_subject_id": "subj-os",
                "source_subject_name": "Computer Architecture",
                "target_subject_name": "Operating Systems",
                "type": "prerequisite_of",
                "strength": 5,
                "scope": "cross_subject",
                "reason": "The hardware MMU is the physical prerequisite providing page translation and page fault exceptions to the OS pager.",
                "industry_example": "ARM Cortex and x86 MMU circuits raise page fault exceptions that transfer execution directly to Linux page swap handlers.",
                "status": "approved",
                "locked": True,
                "evidence": [
                    {"snippet": "The MMU hardware contains the page table walker and TLB translating virtual CPU addresses."},
                    {"snippet": "Operating systems configure hardware page directory registers so the MMU can perform address translation."},
                ],
                "snippet_a": "The MMU hardware contains the page table walker and TLB translating virtual CPU addresses.",
                "snippet_b": "Operating systems configure hardware page directory registers so the MMU can perform address translation.",
            },
            # Strength 4: Strong architectural parallels
            {
                "id": "cross-link-2",
                "source": "t-os-2",
                "target": "t-dbms-1",
                "source_keyword": "Virtual Memory & Paging",
                "target_keyword": "Buffer Pool Management",
                "source_subject_id": "subj-os",
                "target_subject_id": "subj-dbms",
                "source_subject_name": "Operating Systems",
                "target_subject_name": "Database Management Systems",
                "type": "same_concept",
                "strength": 4,
                "scope": "cross_subject",
                "reason": "Both manage fixed-size memory frames (pages vs buffer frames) and apply eviction policies like LRU when main memory is exhausted.",
                "industry_example": "PostgreSQL buffer manager implements clock-sweep eviction to cache 8KB table disk blocks in RAM similarly to OS page replacement.",
                "status": "approved",
                "locked": True,
                "evidence": [
                    {"snippet": "Paging divides virtual memory into fixed 4KB chunks, swapping pages between RAM and swap disk when physical capacity is reached."},
                    {"snippet": "The database buffer manager maintains an in-memory frame cache of disk pages to minimize expensive secondary storage I/O."},
                ],
                "snippet_a": "Paging divides virtual memory into fixed 4KB chunks, swapping pages between RAM and swap disk when physical capacity is reached.",
                "snippet_b": "The database buffer manager maintains an in-memory frame cache of disk pages to minimize expensive secondary storage I/O.",
            },
            {
                "id": "cross-link-3",
                "source": "t-arch-1",
                "target": "t-os-3",
                "source_keyword": "CPU Cache Hierarchy",
                "target_keyword": "Mutex & Semaphore",
                "source_subject_id": "subj-arch",
                "target_subject_id": "subj-os",
                "source_subject_name": "Computer Architecture",
                "target_subject_name": "Operating Systems",
                "type": "prerequisite_of",
                "strength": 4,
                "scope": "cross_subject",
                "reason": "Hardware atomic primitives (test-and-set, compare-and-swap) and cache coherency protocols (MESI) provide the hardware synchronization foundation for OS mutexes.",
                "industry_example": "Linux kernel futexes use atomic compare-and-swap CPU instructions to acquire locks in user space without kernel transition if uncontended.",
                "status": "approved",
                "locked": True,
                "evidence": [
                    {"snippet": "Hardware atomic read-modify-write memory operations require cache line locking or bus lock arbitration."},
                    {"snippet": "Operating system mutexes and spinlocks use atomic hardware CPU instructions to prevent race conditions across parallel threads."},
                ],
                "snippet_a": "Hardware atomic read-modify-write memory operations require cache line locking or bus lock arbitration.",
                "snippet_b": "Operating system mutexes and spinlocks use atomic hardware CPU instructions to prevent race conditions across parallel threads.",
            },
            {
                "id": "cross-link-5",
                "source": "t-dbms-2",
                "target": "t-os-3",
                "source_keyword": "Two-Phase Locking (2PL)",
                "target_keyword": "Mutex & Semaphore",
                "source_subject_id": "subj-dbms",
                "target_subject_id": "subj-os",
                "source_subject_name": "Database Management Systems",
                "target_subject_name": "Operating Systems",
                "type": "same_concept",
                "strength": 4,
                "scope": "cross_subject",
                "reason": "Both apply concurrency control barriers to guarantee serialized execution and prevent dirty reads / data corruption during concurrent execution.",
                "industry_example": "Financial database transaction engines acquire exclusive record locks following rigorous 2PL protocols to guarantee serializability.",
                "status": "approved",
                "locked": True,
                "evidence": [
                    {"snippet": "Two-Phase Locking ensures conflict serializability by requiring transactions to acquire all locks in a growing phase before releasing any."},
                    {"snippet": "Mutual exclusion semaphores ensure that only one concurrent thread enters a critical code section at any given time."},
                ],
                "snippet_a": "Two-Phase Locking ensures conflict serializability by requiring transactions to acquire all locks in a growing phase before releasing any.",
                "snippet_b": "Mutual exclusion semaphores ensure that only one concurrent thread enters a critical code section at any given time.",
            },
            # Strength 3: Moderate practical bridge
            {
                "id": "cross-link-4",
                "source": "t-arch-2",
                "target": "t-cn-3",
                "source_keyword": "Direct Memory Access (DMA)",
                "target_keyword": "Packet Encapsulation",
                "source_subject_id": "subj-arch",
                "target_subject_id": "subj-networks",
                "source_subject_name": "Computer Architecture",
                "target_subject_name": "Computer Networks",
                "type": "applies_in",
                "strength": 3,
                "scope": "cross_subject",
                "reason": "Network Interface Cards (NICs) transfer incoming packet frames directly into host RAM via DMA without CPU cycle overhead.",
                "industry_example": "High-speed 10GbE network cards utilize ring buffers and DMA transfers to ingest line-rate packets into kernel memory.",
                "status": "approved",
                "locked": True,
                "evidence": [
                    {"snippet": "DMA controllers bypass the central processor to transfer blocks of peripheral data directly into physical system memory."},
                    {"snippet": "Network interface adapters use DMA to offload frame transfer from the CPU during packet transmission."},
                ],
                "snippet_a": "DMA controllers bypass the central processor to transfer blocks of peripheral data directly into physical system memory.",
                "snippet_b": "Network interface adapters use DMA to offload frame transfer from the CPU during packet transmission.",
            },
            # Strength 2: Algorithmic heuristic parallel
            {
                "id": "cross-link-7",
                "source": "t-cn-5",
                "target": "t-dbms-5",
                "source_keyword": "BGP Routing",
                "target_keyword": "Query Optimization",
                "source_subject_id": "subj-networks",
                "target_subject_id": "subj-dbms",
                "source_subject_name": "Computer Networks",
                "target_subject_name": "Database Management Systems",
                "type": "applies_in",
                "strength": 2,
                "scope": "cross_subject",
                "reason": "Both systems use graph path cost models (AS-path length vs join tree disk I/O costs) to pick optimal transmission routes.",
                "industry_example": "Distributed database partition query engines evaluate network hop latency similarly to routing protocols.",
                "status": "approved",
                "locked": True,
                "evidence": [
                    {"snippet": "BGP algorithms evaluate path metrics to find the most cost-effective autonomous system transit."},
                    {"snippet": "Relational query optimizers calculate CPU and I/O cost formulas to evaluate join order permutations."},
                ],
                "snippet_a": "BGP algorithms evaluate path metrics to find the most cost-effective autonomous system transit.",
                "snippet_b": "Relational query optimizers calculate CPU and I/O cost formulas to evaluate join order permutations.",
            },
            # Strength 1: Structural naming convention similarity
            {
                "id": "cross-link-6",
                "source": "t-cn-4",
                "target": "t-os-5",
                "source_keyword": "DNS Resolution",
                "target_keyword": "File System Inodes",
                "source_subject_id": "subj-networks",
                "target_subject_id": "subj-os",
                "source_subject_name": "Computer Networks",
                "target_subject_name": "Operating Systems",
                "type": "same_concept",
                "strength": 1,
                "scope": "cross_subject",
                "reason": "Both structures use hierarchical tree path resolution (domain dots vs directory slashes) to resolve human-readable labels to binary addresses.",
                "industry_example": "Apache and Nginx virtual host mapping converts DNS hostname headers directly to root filesystem directory paths.",
                "status": "approved",
                "locked": True,
                "evidence": [
                    {"snippet": "DNS resolves hostnames hierarchically from root down to top-level domains."},
                    {"snippet": "Linux filesystem directories resolve paths starting from root inode down to leaf files."},
                ],
                "snippet_a": "DNS resolves hostnames hierarchically from root down to top-level domains.",
                "snippet_b": "Linux filesystem directories resolve paths starting from root inode down to leaf files.",
            },
        ]

        # Intra-subject (same-subject) links to showcase fading
        same_subject_links = [
            # Networks
            {"id": "same-cn-1", "source": "t-cn-1", "target": "t-cn-2", "source_keyword": "Socket Programming", "target_keyword": "TCP Flow Control", "source_subject_id": "subj-networks", "target_subject_id": "subj-networks", "source_subject_name": "Computer Networks", "target_subject_name": "Computer Networks", "type": "part_of", "strength": 4, "scope": "same_subject", "reason": "TCP sockets adhere to flow control sliding windows when sending.", "industry_example": "Socket buffer limits.", "status": "approved", "locked": False, "evidence": [{"snippet": "Socket send calls block when TCP receiver window drops to zero."}], "snippet_a": "Socket send calls block when TCP receiver window drops to zero.", "snippet_b": None},
            {"id": "same-cn-2", "source": "t-cn-3", "target": "t-cn-5", "source_keyword": "Packet Encapsulation", "target_keyword": "BGP Routing", "source_subject_id": "subj-networks", "target_subject_id": "subj-networks", "source_subject_name": "Computer Networks", "target_subject_name": "Computer Networks", "type": "prerequisite_of", "strength": 3, "scope": "same_subject", "reason": "BGP packets encapsulate within TCP frames.", "industry_example": "BGP peering.", "status": "approved", "locked": False, "evidence": [{"snippet": "BGP routers encapsulate path attributes in TCP port 179 packets."}], "snippet_a": "BGP routers encapsulate path attributes in TCP port 179 packets.", "snippet_b": None},
            # OS
            {"id": "same-os-1", "source": "t-os-1", "target": "t-os-5", "source_keyword": "System Calls", "target_keyword": "File System Inodes", "source_subject_id": "subj-os", "target_subject_id": "subj-os", "source_subject_name": "Operating Systems", "target_subject_name": "Operating Systems", "type": "applies_in", "strength": 4, "scope": "same_subject", "reason": "Open/read system calls look up disk blocks via inodes.", "industry_example": "ext4 file lookup.", "status": "approved", "locked": False, "evidence": [{"snippet": "The sys_open call resolves paths by traversing directory inodes."}], "snippet_a": "The sys_open call resolves paths by traversing directory inodes.", "snippet_b": None},
            {"id": "same-os-2", "source": "t-os-3", "target": "t-os-4", "source_keyword": "Mutex & Semaphore", "target_keyword": "Process Scheduling", "source_subject_id": "subj-os", "target_subject_id": "subj-os", "source_subject_name": "Operating Systems", "target_subject_name": "Operating Systems", "type": "applies_in", "strength": 4, "scope": "same_subject", "reason": "Blocked mutexes yield CPU time slices to runnable threads.", "industry_example": "Thread context switching.", "status": "approved", "locked": False, "evidence": [{"snippet": "Threads waiting on unavailable mutexes enter sleep queues."}], "snippet_a": "Threads waiting on unavailable mutexes enter sleep queues.", "snippet_b": None},
            # DBMS
            {"id": "same-dbms-1", "source": "t-dbms-1", "target": "t-dbms-4", "source_keyword": "Buffer Pool Management", "target_keyword": "Write-Ahead Logging (WAL)", "source_subject_id": "subj-dbms", "target_subject_id": "subj-dbms", "source_subject_name": "Database Management Systems", "target_subject_name": "Database Management Systems", "type": "prerequisite_of", "strength": 5, "scope": "same_subject", "reason": "Dirty buffer pool pages cannot be flushed until WAL records are written.", "industry_example": "ARIES recovery protocol.", "status": "approved", "locked": False, "evidence": [{"snippet": "WAL protocol guarantees changes are durable before page flush."}], "snippet_a": "WAL protocol guarantees changes are durable before page flush.", "snippet_b": None},
            {"id": "same-dbms-2", "source": "t-dbms-3", "target": "t-dbms-5", "source_keyword": "B+ Tree Indexing", "target_keyword": "Query Optimization", "source_subject_id": "subj-dbms", "target_subject_id": "subj-dbms", "source_subject_name": "Database Management Systems", "target_subject_name": "Database Management Systems", "type": "applies_in", "strength": 4, "scope": "same_subject", "reason": "Optimizer evaluates index scan costs vs sequential table scans.", "industry_example": "EXPLAIN plan analysis.", "status": "approved", "locked": False, "evidence": [{"snippet": "Cost models calculate leaf-page depth to determine index feasibility."}], "snippet_a": "Cost models calculate leaf-page depth to determine index feasibility.", "snippet_b": None},
            # Arch
            {"id": "same-arch-1", "source": "t-arch-1", "target": "t-arch-5", "source_keyword": "CPU Cache Hierarchy", "target_keyword": "Memory Management Unit (MMU)", "source_subject_id": "subj-arch", "target_subject_id": "subj-arch", "source_subject_name": "Computer Architecture", "target_subject_name": "Computer Architecture", "type": "prerequisite_of", "strength": 5, "scope": "same_subject", "reason": "TLB is a specialized L1 cache on the MMU caching virtual-to-physical address translations.", "industry_example": "TLB hit rate optimization.", "status": "approved", "locked": False, "evidence": [{"snippet": "Translation Lookaside Buffers cache page table entries in hardware."}], "snippet_a": "Translation Lookaside Buffers cache page table entries in hardware.", "snippet_b": None},
            {"id": "same-arch-2", "source": "t-arch-3", "target": "t-arch-4", "source_keyword": "Instruction Pipelining", "target_keyword": "Interrupt Handling", "source_subject_id": "subj-arch", "target_subject_id": "subj-arch", "source_subject_name": "Computer Architecture", "target_subject_name": "Computer Architecture", "type": "contrasts_with", "strength": 3, "scope": "same_subject", "reason": "Hardware interrupts flush the execution pipeline stages causing latency bubbles.", "industry_example": "Pipeline hazards.", "status": "approved", "locked": False, "evidence": [{"snippet": "Precise interrupt handling drains or invalidates in-flight instructions."}], "snippet_a": "Precise interrupt handling drains or invalidates in-flight instructions.", "snippet_b": None},
        ]

        all_links = cross_links + same_subject_links

        return {
            "scope": "cross_subject",
            "subjects": subjects,
            "nodes": all_nodes,
            "links": all_links,
            "stats": {
                "node_count": len(all_nodes),
                "link_count": len(all_links),
                "cross_subject_links": len(cross_links),
                "same_subject_links": len(same_subject_links),
                "is_synthetic": True,
            },
        }


synthetic_graph_service = SyntheticGraphService()

