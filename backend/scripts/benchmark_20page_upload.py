"""
Benchmark Script for Quality Gate G07:
Measures processing time for an incremental update on a 20-page lecture notes PDF.
Target: <= 90 seconds (Quality Gate G07, Risk R07).
"""

import asyncio
import io
import logging
import os
import time
import uuid
from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from backend.app.database import get_db_cursor
from backend.app.services.job_worker import process_document_job
from backend.app.services.storage import storage_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("BenchmarkG07")


def generate_20page_pdf() -> bytes:
    """
    Synthesizes a 20-page typed lecture PDF covering Operating Systems topics.
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)

    topics_per_page = [
        ("Process Scheduling & Queues", "Operating systems schedule processes using ready, wait, and terminated queues. Shortest Job First optimizes average turnaround time."),
        ("Round Robin Scheduling", "Round Robin assigns a fixed time quantum to each runnable process in circular order. Preemption guarantees interactive responsiveness."),
        ("Deadlock Conditions", "Coffman conditions define deadlock: mutual exclusion, hold and wait, no preemption, and circular wait. Breaking any condition prevents deadlock."),
        ("Banker's Algorithm", "Dijkstra's Banker's Algorithm prevents deadlocks by evaluating safe states before granting resource allocation requests."),
        ("Virtual Memory Architecture", "Virtual memory decouples the programmer's logical address space from physical RAM using hardware MMU translation."),
        ("Paging and Frame Allocation", "Paging divides logical memory into fixed-size pages and physical memory into page frames, eliminating external fragmentation."),
        ("Page Replacement: LRU", "Least Recently Used replaces the frame untouched for the longest time, tracking access via reference bits or timestamps."),
        ("Thrashing & Working Set", "Thrashing occurs when an OS spends more time swapping pages than executing instructions. Working set models regulate page allocation."),
        ("File System Superblocks", "Superblocks store global file system metadata, including total blocks, inode tables, and free block bitmaps."),
        ("Inode Pointers & Indexing", "Inodes map files to disk blocks via direct, single indirect, double indirect, and triple indirect block pointers."),
        ("Ext4 Journaling Modes", "Journaling logs block updates before committing to disk, preventing structural corruption during sudden power losses."),
        ("RAID Storage Architectures", "RAID 0 stripes for speed, RAID 1 mirrors for redundancy, and RAID 5 uses distributed parity across disk drives."),
        ("Inter-Process Communication", "IPC enables processes to communicate via shared memory, message queues, pipes, and network sockets."),
        ("POSIX Semaphores", "Semaphores provide signaling primitives: wait decrements the counter, and post increments it, preventing race conditions."),
        ("Mutexes & Futexes", "Mutexes offer mutual exclusion locks with ownership semantics. Fast userspace mutexes avoid expensive kernel syscalls when uncontended."),
        ("Memory-Mapped I/O", "mmap maps file contents directly into a process's virtual address space, reducing read and write buffer copies."),
        ("Context Switching Overhead", "A context switch saves registers, program counters, and flushes TLBs, imposing measurable CPU latency."),
        ("System Calls & Trap Tables", "User programs transition into kernel space using trap instructions, indexing the Interrupt Descriptor Table (IDT)."),
        ("Device Drivers & DMA", "Direct Memory Access allows peripherals to transfer data directly into system RAM without saturating the CPU."),
        ("Real-Time Operating Systems", "RTOS guarantees bounded deterministic execution deadlines for avionics and industrial robotics controllers."),
    ]

    for page_num, (title, content) in enumerate(topics_per_page, 1):
        c.setFont("Helvetica-Bold", 16)
        c.drawString(54, 730, f"Module 3: Advanced Operating Systems — Lecture {page_num}")
        c.setFont("Helvetica-Bold", 13)
        c.drawString(54, 700, f"Section {page_num}.1: {title}")
        c.setFont("Helvetica", 10)
        c.drawString(54, 675, content)
        c.drawString(54, 650, "Real-world engineering relevance: Implemented extensively across enterprise kernels.")
        c.drawString(54, 625, "System architecture: Hardware MMU, cache coherency protocols, and POSIX conformance.")
        c.drawString(54, 50, f"Page {page_num} of 20 — StudyGraph Verification Dataset")
        c.showPage()

    c.save()
    buf.seek(0)
    return buf.getvalue()


async def run_g07_benchmark():
    """
    Executes the 20-page incremental processing benchmark.
    """
    logger.info("=== Starting Quality Gate G07 Benchmark: 20-Page Incremental Processing ===")
    
    test_user_id = "00000000-0000-0000-0000-000000000077"
    subject_id = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())
    filename = "OS_Comprehensive_20Pages.pdf"

    # Step 1: Generate PDF
    pdf_bytes = generate_20page_pdf()
    logger.info(f"Generated 20-page benchmark PDF: {len(pdf_bytes)} bytes")

    # Step 2: Setup database fixture
    with get_db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO users (id, email, name)
            VALUES (%s, 'g07_benchmark@studygraph.io', 'G07 Benchmark User')
            ON CONFLICT (id) DO NOTHING;
            """,
            (test_user_id,),
        )
        cur.execute(
            """
            INSERT INTO subjects (id, user_id, name)
            VALUES (%s, %s, 'Benchmark Subject OS')
            ON CONFLICT (id) DO NOTHING;
            """,
            (subject_id, test_user_id),
        )

    # Step 3: Upload to storage
    storage_path = f"{test_user_id}/{subject_id}/module_3/{filename}"
    saved_path = await storage_service.upload_file(
        file_bytes=pdf_bytes,
        storage_path=storage_path,
        content_type="application/pdf",
    )
    logger.info(f"Uploaded benchmark PDF to storage: {saved_path}")

    with get_db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO documents (id, subject_id, module_no, filename, type, source_kind, status, storage_path)
            VALUES (%s, %s, 3, %s, 'pdf', 'notes', 'queued', %s);
            """,
            (doc_id, subject_id, filename, saved_path),
        )

    # Step 4: Run timer for pipeline execution
    start_time = time.perf_counter()
    logger.info("Starting background pipeline processing timer...")

    await process_document_job(document_id=doc_id, user_id=test_user_id)

    elapsed_seconds = time.perf_counter() - start_time
    logger.info(f"=== Incremental pipeline completed in {elapsed_seconds:.2f} seconds ===")

    # Step 5: Verify results and quality gate target
    with get_db_cursor() as cur:
        cur.execute("SELECT status, summary FROM documents WHERE id = %s;", (doc_id,))
        doc_status, doc_summary = cur.fetchone()

        cur.execute("SELECT COUNT(*) FROM chunks WHERE document_id = %s;", (doc_id,))
        chunk_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM topics WHERE subject_id = %s;", (subject_id,))
        topic_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM clusters WHERE subject_id = %s;", (subject_id,))
        cluster_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM graph_versions WHERE subject_id = %s;", (subject_id,))
        version_count = cur.fetchone()[0]

    logger.info(f"Verification Results:")
    logger.info(f"  - Document Status: {doc_status}")
    logger.info(f"  - Summary: '{doc_summary}'")
    logger.info(f"  - Chunks extracted: {chunk_count}")
    logger.info(f"  - Topics extracted: {topic_count}")
    logger.info(f"  - Clusters formed: {cluster_count}")
    logger.info(f"  - Graph versions: {version_count}")

    target_met = elapsed_seconds <= 90.0
    logger.info("------------------------------------------------------------")
    logger.info(f"Quality Gate G07 Target: <= 90.0 seconds")
    logger.info(f"Measured Time:           {elapsed_seconds:.2f} seconds")
    logger.info(f"Status:                  {'PASSED' if target_met else 'FAILED'}")
    logger.info("------------------------------------------------------------")

    # Cleanup test benchmark data
    with get_db_cursor() as cur:
        cur.execute("DELETE FROM graph_cache WHERE user_id = %s;", (test_user_id,))
        cur.execute("DELETE FROM graph_versions WHERE user_id = %s;", (test_user_id,))
        cur.execute("DELETE FROM clusters WHERE subject_id = %s;", (subject_id,))
        cur.execute("DELETE FROM edges WHERE topic_a IN (SELECT id FROM topics WHERE subject_id = %s) OR topic_b IN (SELECT id FROM topics WHERE subject_id = %s);", (subject_id, subject_id))
        cur.execute("DELETE FROM link_candidates WHERE topic_a IN (SELECT id FROM topics WHERE subject_id = %s) OR topic_b IN (SELECT id FROM topics WHERE subject_id = %s);", (subject_id, subject_id))
        cur.execute("DELETE FROM topic_sources WHERE topic_id IN (SELECT id FROM topics WHERE subject_id = %s);", (subject_id,))
        cur.execute("DELETE FROM topics WHERE subject_id = %s;", (subject_id,))
        cur.execute("DELETE FROM chunks WHERE document_id = %s;", (doc_id,))
        cur.execute("DELETE FROM documents WHERE id = %s;", (doc_id,))
        cur.execute("DELETE FROM subjects WHERE id = %s;", (subject_id,))
        cur.execute("DELETE FROM users WHERE id = %s;", (test_user_id,))

    return {
        "elapsed_seconds": elapsed_seconds,
        "target_met": target_met,
        "summary": doc_summary,
        "chunk_count": chunk_count,
        "topic_count": topic_count,
    }


if __name__ == "__main__":
    result = asyncio.run(run_g07_benchmark())
    print(f"\nFinal Benchmark Output: {result['elapsed_seconds']:.2f}s | Gate G07: {'PASSED' if result['target_met'] else 'FAILED'}")

