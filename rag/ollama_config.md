# Cấu hình Ollama/RAG

Stack local đề xuất:

- Ollama model: `llama3.1`, `qwen2.5`, `mistral` hoặc model local khác có sẵn.
- Embedding model: model embedding local được framework RAG hỗ trợ.
- Vector store: Chroma, LanceDB, FAISS hoặc SQLite-based vector store.
- Retrieval corpus: các file liệt kê bên dưới.

## File đưa vào knowledge base

Nên index:

- `data/metadata/tourism_operating_system_blueprint.md`
- `data/metadata/dataset_audit.csv`
- `data/metadata/data_quality_scores.csv`
- `metadata/dataset_status_catalog.csv`
- `metadata/kpi_thresholds_by_destination.csv`
- `metadata/economic_proof_catalog.csv`
- `data/metadata/kpi_catalog_operational.csv`
- `data/metadata/kpi_methodology.md`
- `data/metadata/missing_dataset_registry.csv`
- `data/metadata/destination_registry.csv`
- `data/metadata/destination_network_edges.csv`
- `docs/methodology.md`
- `docs/limitations.md`
- `docs/economic_proof.md`
- `docs/economic_proof_mvp.md`

## Quy tắc assistant

Assistant phải:

- Nêu dataset hoặc registry được dùng cho từng câu trả lời.
- Tách rõ dữ liệu quan sát được, proxy, schema-only, missing và recommendation.
- Trả confidence dựa trên data coverage.
- Không được tuyên bố occupancy thật, congestion thật, revenue thật hoặc crowd density thật nếu nguồn bắt buộc chưa tồn tại.
- Giải thích tradeoff kinh tế, không chỉ giải thích score kỹ thuật.

## Mẫu API local

```http
POST http://localhost:11434/api/chat
```

Prompt nên gồm retrieved context và câu hỏi của người dùng.
