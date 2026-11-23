# Phase 2 evaluation

Measured on the Windows development environment using Python 3.14, PyTorch 2.15.0 CPU, SentenceTransformers 5.7.0, Qdrant Client 1.20.0 local mode and the seeded PostgreSQL demo. Command: `python -m evaluation.run --stress-tables 100`. MiniLM weights were cached on disk before this run. The benchmark started a fresh process and used a temporary Qdrant index.

| Metric | Full schema | Schema RAG |
|---|---:|---:|
| Table recall@4 before FK expansion | Unranked | 97.7% |
| Required table recall in prompt | 100% | 100% |
| Required FK edge coverage | 100% | 100% |
| Mean extra tables per positive case | 3.344 | 0 |
| Positive cases matching independently specified rows | 32/32 | 32/32 |
| Negative or ambiguous cases handled | 8/8 | 8/8 |
| Mean schema-context characters | 612 | 237.8 |
| Mean retrieval latency | Skipped | 9.6 ms |
| Mean ASGI-to-result latency | 8.2 ms | 16.3 ms |
| P95 ASGI-to-result latency | 15.8 ms | 21.6 ms |

The 28-document initial index took 9.55 s, including CPU model load. The process peak working set was 83.2 MiB before indexing and 628.8 MiB afterward. This is process-wide memory, including the embedding runtime, rather than the vector index's standalone footprint.

The isolated stress run added 100 synthetic metadata-only tables, bringing the total to 628 documents. Reindexing with the already-loaded model took 5.31 s. The process peak working set reached 639.1 MiB. Mean retrieval time was 20.8 ms after prebuilding the expanded index. Recall@4 was 97.7%, and post-expansion table recall and required FK coverage were both 100%. The expanded full-schema context was 14,976 characters. Mean retrieved context was 237.8 characters. Stress results measure retrieval only and use zero added PostgreSQL tables.

Both query modes used fixture SQL gated on the presence of the expected tables and relationships. PostgreSQL executed the SQL and results were compared against the fixture oracle. The latency values omit Groq and browser network calls. The small dataset, curated questions and synthetic decoys limit what this run can establish about accuracy or performance in larger deployments. RAG reduced context size in this run and added local processing time.
