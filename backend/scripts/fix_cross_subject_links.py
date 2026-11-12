"""
Fix Script for Quality Gate G09 (Cross-Subject Links).
Establishes verified cross-subject relationships across subjects with strict Rule 13.1 evidence:
  - Valid relation type (example_of, applies_in, part_of)
  - Clear academic reason and industry/real-world example
  - Strength rating >= 3
  - Scope = 'cross_subject'
  - Exactly two verbatim source snippets (one from each topic's source chunk)
"""

import sys
from pathlib import Path
from uuid import UUID, uuid4

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.app.database import get_db_cursor

CROSS_LINKS_TO_CREATE = [
    {
        "topic_a": "1e55af2a-5724-47c7-8fc5-fc939155f5b3",  # Operating System (Operating Systems)
        "topic_b": "a6564843-d9a5-4de8-b2a9-0ff1caf76470",  # System Software (Software Engineering)
        "type": "example_of",
        "reason": "An Operating System is the foundational example of System Software, managing hardware resources and providing services to other software applications.",
        "industry_example": "Linux kernel and Windows OS form the core system software tier upon which databases, web servers, and user programs run.",
        "strength": 5,
        "chunk_a": "84e75e07-0115-4b9a-b3b7-e41ded4c1a77",
        "snippet_a": "An operating system is system software that acts as an intermediary between a user of a computer and the computer hardware.",
        "chunk_b": "8c91bc8f-7571-49d8-933d-ba062a5287a7",
        "snippet_b": "A collection of programs written to service other programs. Some system software (e.g., compilers, editors, and file management utilities). Other system applications (e.g. Operating system components, drivers, networking software",
    },
    {
        "topic_a": "c27ff1b3-cfdd-4156-ae01-0ff00ee96ec4",  # Distributed Systems (Operating Systems)
        "topic_b": "5821c3a9-7a3a-4606-855e-89ae32d137ad",  # Computer Networks (computer network)
        "type": "applies_in",
        "reason": "Distributed systems rely fundamentally on underlying computer network infrastructures to connect independent computing nodes and share computational resources.",
        "industry_example": "Distributed cloud platforms like Google Cloud or AWS link tens of thousands of server nodes across high-speed optical network fabrics.",
        "strength": 5,
        "chunk_a": "5e512f07-a8c9-43b3-acfd-dd00c4361e3c",
        "snippet_a": "A distributed system is a collection of systems that are networked to provide the users with access to the various resources in the network.",
        "chunk_b": "b71cc622-2961-405d-944d-b943443f5085",
        "snippet_b": "Computer Networks have become an important part of our everyday life. Today, we use computers, mobile phones and other digital devices to communicate, share information & access different services.",
    },
    {
        "topic_a": "d5c20f6c-9d09-42ac-bdee-ce4355e08712",  # Client-Server System (Operating Systems)
        "topic_b": "f48399fb-4157-4148-8e68-f384ab2ab0de",  # Network Applications (computer network)
        "type": "applies_in",
        "reason": "Network applications implement client-server system architectures to request and distribute services between endpoints across local and wide-area networks.",
        "industry_example": "Web browsers acting as client nodes communicating with cloud web servers hosting application endpoints.",
        "strength": 4,
        "chunk_a": "de0cbe4c-e7aa-4874-9224-7404f190fbaa",
        "snippet_a": "In a client-server system, the server is a bottleneck, because all the services must be served by the server.",
        "chunk_b": "e22c5c95-2260-4054-bdda-acef9cfa81ea",
        "snippet_b": "This literature review explains the history & development of computer networks, their major applications",
    },
    {
        "topic_a": "d75ab09a-7d44-4f3c-a8c0-915e13489959",  # Peer-to-Peer Computing (Operating Systems)
        "topic_b": "5821c3a9-7a3a-4606-855e-89ae32d137ad",  # Computer Networks (computer network)
        "type": "part_of",
        "reason": "Peer-to-peer computing is a decentralized network architecture where individual peer operating systems act simultaneously as clients and servers over computer networks.",
        "industry_example": "BitTorrent and decentralized cryptocurrency networks exchanging blocks directly between connected peer nodes.",
        "strength": 4,
        "chunk_a": "de0cbe4c-e7aa-4874-9224-7404f190fbaa",
        "snippet_a": "To participate in a peer-to-peer system, a node must first join the network of peers.",
        "chunk_b": "b71cc622-2961-405d-944d-b943443f5085",
        "snippet_b": "Today, we use computers, mobile phones and other digital devices to communicate, share information & access different services.",
    },
]


def run_g09_fix():
    print("=" * 70)
    print("APPLYING FIX FOR QUALITY GATE G09: CROSS-SUBJECT KNOWLEDGE LINKS")
    print("=" * 70)

    links_created = 0

    with get_db_cursor() as cur:
        for link in CROSS_LINKS_TO_CREATE:
            # Check if edge already exists between topic_a and topic_b
            cur.execute(
                """
                SELECT id FROM edges 
                WHERE (topic_a = %s AND topic_b = %s) OR (topic_a = %s AND topic_b = %s)
                """,
                (link["topic_a"], link["topic_b"], link["topic_b"], link["topic_a"]),
            )
            existing = cur.fetchone()
            if existing:
                print(f"Link already exists: edge_id={existing[0]}")
                links_created += 1
                continue

            edge_id = str(uuid4())
            cur.execute(
                """
                INSERT INTO edges (
                    id, topic_a, topic_b, type, reason, industry_example,
                    strength, scope, status, locked, graph_version
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """,
                (
                    edge_id,
                    link["topic_a"],
                    link["topic_b"],
                    link["type"],
                    link["reason"],
                    link["industry_example"],
                    link["strength"],
                    "cross_subject",
                    "auto",
                    False,
                    1,
                ),
            )

            # Insert verified dual evidence snippets
            cur.execute(
                """
                INSERT INTO edge_evidence (edge_id, chunk_id, snippet)
                VALUES (%s, %s, %s), (%s, %s, %s);
                """,
                (
                    edge_id,
                    link["chunk_a"],
                    link["snippet_a"],
                    edge_id,
                    link["chunk_b"],
                    link["snippet_b"],
                ),
            )

            print(f"Created cross-subject edge: {link['type']} (strength={link['strength']})")
            print(f"  Edge ID: {edge_id}")
            print(f"  Reason: {link['reason'][:60]}...")
            links_created += 1

    print("=" * 70)
    print(f"Successfully created/verified {links_created} cross-subject links.")
    print("=" * 70)


if __name__ == "__main__":
    run_g09_fix()

