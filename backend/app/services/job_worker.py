"""
Background Job Processing for StudyGraph.
Relies on:
  - Decision D07: FastAPI BackgroundTasks.
  - Decision D08: Google Gemini Flash for scans/handwriting.
  - Decision D09: Google Gemini Flash for topic extraction & link judging.
  - Decision D10: Google text-embedding-004 for vector search.
  - Decision D11: NetworkX Louvain Community Detection for cluster hierarchy.
  - Decision D15: pdfplumber + pypdf + python-pptx for typed text.
  - Pipeline Steps 1-14: Complete incremental ingestion, linking, clustering, and caching.
"""

import logging
from typing import Optional

from backend.app.database import get_db_cursor
from backend.app.schemas.candidate import CandidateSearchParams
from backend.app.services.candidate_finder import CandidateFinderService
from backend.app.services.cluster_service import cluster_service
from backend.app.services.dedupe_service import DedupeService
from backend.app.services.embedding_service import EmbeddingService
from backend.app.services.exam_service import exam_service
from backend.app.services.extractor import extractor_service
from backend.app.services.graph_service import graph_service
from backend.app.services.link_judge import LinkJudgeService
from backend.app.services.storage import storage_service
from backend.app.services.syllabus_service import syllabus_service
from backend.app.services.topic_extractor import topic_extractor_service

logger = logging.getLogger(__name__)


def update_document_status(
    document_id: str,
    status: str,
    error_message: Optional[str] = None,
    summary: Optional[str] = None,
) -> None:
    """
    Updates the status, optional error message, and change summary of a document in PostgreSQL.
    """
    with get_db_cursor() as cursor:
        cursor.execute(
            """
            UPDATE documents 
            SET status = %s,
                error_message = %s,
                summary = COALESCE(%s, summary)
            WHERE id = %s;
            """,
            (status, error_message, summary, document_id),
        )


async def process_document_job(document_id: str, user_id: str) -> None:
    """
    Background worker executed via FastAPI BackgroundTasks (Decision D07).
    Executes the complete incremental pipeline (Steps 1-14) for a newly uploaded document:
      1. Fetch document metadata & download file bytes.
      2. Extract text/vision chunks for ONLY this new document (Incremental rule).
      3. Save chunks and generate embeddings for new chunks.
      4. Extract topics grounded in new chunks with 4-line limit (Task T05).
      5. Embed new topics and run deduplication within subject (Task T07).
      6. Discover candidate links between NEW topics and ALL existing topics (Task T08, Incremental).
      7. Run LLM Judge on pending candidates with code-level snippet verification (Task T09).
      8. Respect locks & user edits (Task T10).
      9. Build 2-tier cluster hierarchy using NetworkX Louvain detection (Task T11, D11).
      10. Record immutable graph_versions snapshot with human-readable summary.
      11. Invalidate and refresh pre-compiled graph cache (Task T11, Step 14).
      12. Record summary on document and mark 'done'.
    """
    try:
        # Step 1: Mark status as 'extracting'
        update_document_status(document_id, "extracting")
        logger.info(f"[Job Worker] Document {document_id} transitioned to 'extracting'")

        # Step 2: Fetch document metadata from DB
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                SELECT subject_id, filename, module_no, storage_path, source_kind
                FROM documents
                WHERE id = %s;
                """,
                (document_id,),
            )
            doc_row = cursor.fetchone()

        if not doc_row:
            raise ValueError(f"Document with id {document_id} not found in database.")

        subject_id_raw, filename, module_no, storage_path, source_kind = doc_row
        subject_id = str(subject_id_raw) if subject_id_raw else None
        if not storage_path:
            raise ValueError(f"Document {document_id} has no storage_path recorded.")

        # Step 3: Download file bytes from storage
        file_bytes = await storage_service.download_file(storage_path)
        logger.info(
            f"[Job Worker] Downloaded {len(file_bytes)} bytes for '{filename}' ({storage_path})"
        )

        # Step 4: Extract text and vision chunks for THIS document only (Pipeline Step 2-4)
        extraction_result = extractor_service.extract_document(
            file_bytes=file_bytes,
            filename=filename,
            source_kind=source_kind or "notes",
        )

        logger.info(
            f"[Job Worker] Extracted {len(extraction_result.chunks)} chunks from '{filename}' "
            f"({extraction_result.pages_processed} pages: {extraction_result.direct_pages} direct, "
            f"{extraction_result.vision_pages} vision, {extraction_result.total_tokens} tokens)"
        )

        # Step 5: Save chunks to PostgreSQL (idempotent overwrite for this doc)
        with get_db_cursor() as cursor:
            cursor.execute("DELETE FROM chunks WHERE document_id = %s;", (document_id,))
            for chunk in extraction_result.chunks:
                cursor.execute(
                    """
                    INSERT INTO chunks (document_id, page, text, module_no, method)
                    VALUES (%s, %s, %s, %s, %s);
                    """,
                    (document_id, chunk.page, chunk.text, module_no, chunk.method),
                )

        # Step 5b: If this document is a previous-year question paper, route to Exam Mode parser (T17)
        # instead of creating graph topics/edges from exam questions.
        if (source_kind or "").lower() == "paper" and subject_id:
            pages_by_no = [(chunk.page, chunk.text) for chunk in extraction_result.chunks]
            paper_res = exam_service.ingest_paper_document(
                document_id=document_id,
                subject_id=subject_id,
                filename=filename,
                pages=pages_by_no,
            )
            q_cnt = paper_res.get("questions_extracted", 0)
            paper_summary = (
                f"Parsed {q_cnt} exam question{'s' if q_cnt != 1 else ''} "
                f"and updated repeated-question clusters."
            )
            update_document_status(document_id, "done", summary=paper_summary)
            logger.info(f"[Job Worker] Exam paper {document_id} complete: {paper_summary}")
            return

        # Step 6: Generate embeddings for new chunks (Decision D10)
        logger.info(f"[Job Worker] Generating embeddings for chunks of document {document_id}")
        embedding_service = EmbeddingService()
        try:
            chunks_embedded = embedding_service.embed_unembedded_chunks(document_id)
            logger.info(f"[Job Worker] Generated embeddings for {chunks_embedded} chunks.")
        except Exception as emb_err:
            logger.warning(f"[Job Worker] Chunk embedding encountered non-fatal error: {emb_err}")

        # Step 7: Extract topics from new chunks (Pipeline Step 6, Task T05)
        logger.info(f"[Job Worker] Starting topic extraction for document {document_id}")
        topic_result = topic_extractor_service.process_document_topics(document_id)
        created_topic_ids = topic_result.created_topic_ids
        logger.info(
            f"[Job Worker] Topic extraction complete for {document_id}: "
            f"{len(created_topic_ids)} topics identified, {topic_result.topics_rejected} rejected, "
            f"tokens used: {topic_result.token_usage['total_tokens']}"
        )

        new_links_count = 0
        cross_links_count = 0
        cluster_count = 0

        if subject_id:
            # Step 8: Embed new topics & run deduplication (Pipeline Step 8, Task T07)
            try:
                topics_embedded = embedding_service.embed_unembedded_topics(subject_id)
                logger.info(f"[Job Worker] Embedded {topics_embedded} topics in subject {subject_id}")

                dedupe_service = DedupeService()
                dedupe_res = dedupe_service.run_auto_deduplication(subject_id)
                logger.info(
                    f"[Job Worker] Deduplication finished: {dedupe_res.merges_executed} merges "
                    f"across {dedupe_res.candidates_found} candidates."
                )
            except Exception as ded_err:
                logger.warning(f"[Job Worker] Deduplication encountered non-fatal error: {ded_err}")

            # Step 8b: Match new/unlocked topics against syllabus ghost nodes (Task T18, Feature F16)
            try:
                syl_match_res = syllabus_service.match_subject_topics(
                    subject_id=subject_id,
                    user_id=user_id,
                    refresh_cache=False,
                )
                if syl_match_res.matches_created > 0:
                    logger.info(
                        f"[Job Worker] Lit up {syl_match_res.matches_created} syllabus ghost node(s) "
                        f"(Coverage: {syl_match_res.coverage_percent}%)."
                    )
            except Exception as syl_err:
                logger.warning(f"[Job Worker] Syllabus matching encountered non-fatal error: {syl_err}")

            # Step 9: Incremental Candidate Discovery (Pipeline Step 9, Task T08)
            # Crucial: Evaluates only the newly extracted topics against the existing graph!
            if created_topic_ids:
                try:
                    candidate_finder = CandidateFinderService()
                    cand_params = CandidateSearchParams(
                        subject_id=subject_id,
                        topic_ids=created_topic_ids,
                        include_cross_subject=True,
                    )
                    cand_batch = candidate_finder.find_and_store_candidates(cand_params)
                    logger.info(
                        f"[Job Worker] Candidate finder discovered {cand_batch.total_candidates_found} "
                        f"pairs for new topics ({cand_batch.same_subject_count} same-subject, "
                        f"{cand_batch.cross_subject_count} cross-subject)."
                    )
                except Exception as cand_err:
                    logger.warning(f"[Job Worker] Candidate discovery error (non-fatal): {cand_err}")

            # Step 10: Judge newly discovered candidates (Pipeline Steps 10-11, Tasks T09-T10)
            try:
                link_judge = LinkJudgeService()
                judge_batch = link_judge.judge_pending_candidates(limit=6)
                new_links_count = judge_batch.edges_created
                logger.info(
                    f"[Job Worker] Link judge evaluated candidates: "
                    f"{judge_batch.edges_created} edges created, {judge_batch.candidates_rejected} rejected."
                )
            except Exception as judge_err:
                logger.warning(f"[Job Worker] Link judge error (non-fatal): {judge_err}")

            # Step 11: Louvain Hierarchical Clustering (Pipeline Step 12, Task T11, Decision D11)
            try:
                cluster_res = cluster_service.build_subject_clusters(subject_id)
                cluster_count = cluster_res.get("top_level_count", 0)
                logger.info(
                    f"[Job Worker] Louvain clustering complete: {cluster_count} top-level clusters, "
                    f"{cluster_res.get('sub_cluster_count', 0)} sub-clusters."
                )
            except Exception as clust_err:
                logger.warning(f"[Job Worker] Louvain clustering error (non-fatal): {clust_err}")

        # Step 12: Generate human-readable summary of what changed
        topics_count = len(created_topic_ids)
        summary_text = (
            f"Added {topics_count} topic{'s' if topics_count != 1 else ''}, "
            f"discovered {new_links_count} new link{'s' if new_links_count != 1 else ''}, "
            f"organized into {cluster_count} cluster{'s' if cluster_count != 1 else ''}."
        )

        # Step 13: Record snapshot in graph_versions table (Pipeline Step 12)
        version_id = None
        try:
            version_record = graph_service.record_graph_version(
                user_id=user_id,
                subject_id=subject_id,
                summary=summary_text,
            )
            version_id = version_record["version_id"]
            logger.info(f"[Job Worker] Recorded graph version {version_record['version_number']}: {summary_text}")
        except Exception as v_err:
            logger.warning(f"[Job Worker] Graph version recording error: {v_err}")

        # Step 14: Invalidate and refresh pre-compiled graph cache (Pipeline Step 14, Task T11)
        try:
            graph_service.refresh_and_cache_graph(
                user_id=user_id,
                subject_id=subject_id,
                graph_version_id=version_id,
            )
            logger.info(f"[Job Worker] Graph cache refreshed for subject {subject_id} and cross-subject.")
        except Exception as cache_err:
            logger.warning(f"[Job Worker] Graph cache refresh error: {cache_err}")

        # Step 15: Mark status as 'done' and save summary on document
        update_document_status(document_id, "done", summary=summary_text)
        logger.info(f"[Job Worker] Document {document_id} processing complete: status -> 'done'")

    except Exception as e:
        logger.error(f"[Job Worker] Error processing document {document_id}: {e}", exc_info=True)
        update_document_status(document_id, "failed", error_message=str(e))
