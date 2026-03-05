# Aelin Attachment Parsing & QA Plan (LangChain-Inspired)

## Goal
Enable Aelin Agent to parse user-uploaded attachments (PDF / DOC / DOCX / PPT / PPTX / XLSX / TXT / MD / CSV / JSON / images), answer questions grounded in file content, and return traceable citations.

## 1) Architecture (Decoupled 4 Layers)

### 1.1 File Access Layer
Provide stable tools for the agent to locate and read files without context explosion.

- `ls(path)`
- `glob(pattern)`
- `read_file(path, offset, limit)` (paged read, mandatory)
- `grep(pattern, path, context_lines)`

Large tool outputs are evicted to disk (e.g. `/work/large_tool_results/...`) and only summarized in chat.

### 1.2 Parsing Layer (Unified Parser API)
Normalize heterogeneous files into one canonical artifact:

```json
{
  "doc_id": "sha256:...",
  "source": "uploads/ch1.pptx",
  "text": "full plain text",
  "blocks": [
    {"id":"b1","type":"heading","content":"...","loc":{"page":1}},
    {"id":"b2","type":"paragraph","content":"...","loc":{"page":1}}
  ],
  "tables": [
    {"id":"t1","loc":{"page":2},"rows":[["A","B"],["1","2"]]}
  ],
  "images": [
    {
      "id":"img1",
      "anchor":{"page":3},
      "ocr_text":"...",
      "vision_caption":"..."
    }
  ],
  "metadata": {"file_name":"ch1.pptx","parser":"v1.0"}
}
```

Format routing:
- PDF: text layer extraction; fallback OCR for scanned pages/images; preserve page-level loc.
- DOCX/PPTX/XLSX: OOXML structure parsing (heading/paragraph/table/slide/sheet/cell).
- DOC/PPT/XLS: convert to modern format first (`docx/pptx/xlsx`) then parse.
- Plain text files: decode + normalize directly.

### 1.3 Index Layer (Parse Once, Query Many)
Avoid reparsing for every question.

- Cache key: `doc_id = sha256(file_bytes)` (or `path+size+mtime` fallback).
- Persist:
  - parsed artifact JSON
  - chunks
  - optional embeddings
  - BM25/full-text index
- Retrieval strategy: hybrid (`BM25 + vector + structure-aware`) with RRF/weighted fusion.

### 1.4 Agent Orchestration Layer
Use a deterministic retrieval flow to keep answers stable and explainable.

Recommended tools:
1. `ingest_attachment(attachment_id | path, options)`
2. `attachment_search(query, attachment_ids, top_k, mode)`
3. `answer_with_attachments(question, attachment_ids, citations=true)`

Standard pipeline:
`locate -> parse/cache -> retrieve top-k -> selective deep-read by loc -> answer + citation`

## 2) `attachment_search` Tool Contract

### Input Schema
- `query: string` (required, 1~500)
- `attachment_ids: int[]` (required, <= 20)
- `top_k?: int` (default 5, range 1~20)
- `mode?: "keyword" | "hybrid"` (default `keyword`)
- `workspace_id/session_id?: string` (for isolation)

### Execution Steps
1. Permission check (user/session can access attachments).
2. Search only inside selected attachment chunks.
3. Optional rerank (cross-encoder or LLM reranker).
4. Dedup + truncation (chunk similarity threshold).
5. Return structured hits and model-friendly `content`.

### Output Schema
```json
{
  "content": "[hit1] ...\n[hit2] ...",
  "hits": [
    {
      "chunk_id": "c_102",
      "text": "...",
      "score": 0.87,
      "citation": {
        "attachment_id": 12,
        "file_name": "ch1.pptx",
        "slide": 5,
        "row_range": null
      },
      "metadata": {"doc_id":"sha256:...","block_type":"paragraph"}
    }
  ],
  "artifact": {"total_hits": 23}
}
```

## 3) Citation Rules (Must Have)

Output format examples:
- PDF: `来源：report.pdf，第 12 页，第 3 段`
- PPTX: `来源：deck.pptx，第 5 页（Notes）`
- XLSX: `来源：data.xlsx，Sheet=Summary，B2:D8`

Citations are generated from `loc`/`citation` metadata, not guessed by the model.

## 4) Delivery Plan

### Phase 1 (MVP, 1~2 iterations)
- Add parsing pipeline for `pdf/docx/pptx/xlsx/txt/md/csv/json/images`.
- Add `attachment_chunks` storage + BM25 retrieval.
- Add `attachment_search` tool and agent routing.
- Return citations in final answer.

### Phase 2 (Quality & Scale)
- Hybrid retrieval + rerank.
- Better OCR and table extraction quality.
- Parse queue + retry + observability metrics.

### Phase 3 (Advanced)
- Cross-file QA and comparative reasoning.
- Incremental re-index and background refresh.

## 5) Guardrails

- File size/type limits and clear user-facing errors.
- Timeouts per parser and per tool invocation.
- Strict tenant/session permission boundary.
- Sensitive data redaction support before indexing.

## 6) Success Metrics

- Parse success rate by file type.
- End-to-end QA latency (P50/P95).
- Citation coverage (% answers with valid source loc).
- Retrieval precision@k on internal eval set.
- Reparse avoidance rate (cache hit ratio).
