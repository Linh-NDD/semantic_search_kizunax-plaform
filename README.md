# semantic_search_kizunax-plaform

Built-in RAG and Embedding semantic search from KizunaX Platform

## Kizuna RAG Standalone PoC

Lightweight standalone RAG backend using Kizuna OCR Markdown API, Kizuna Embedding API, Qdrant native binary, and FastAPI.

This service is **retrieval-only**. It does not call `/rag/chat`, does not run a local LLM, and does not generate chatbot answers. It fetches markdown, chunks text, embeds chunks, stores vectors in Qdrant, and returns relevant chunks for any AI Agent to use as context.

## Architecture

```text
Kizuna RAG collections/documents
  -> Kizuna OCR markdown
  -> chunk markdown
  -> Kizuna embeddings bge-m3
  -> Qdrant vector storage
  -> semantic search / mini retrieval chat
  -> any AI Agent
```

## What users must configure

Copy the sample config and set your own API key:

```bash
cp /opt/rag/config/kizuna.example.json /opt/rag/config/kizuna.json
nano /opt/rag/config/kizuna.json
```

Required fields:

```json
{
  "base_url": "https://kizunax.io/api/v1",
  "api_key": "YOUR_KIZUNA_API_KEY",
  "ocr_path": "/rag/documents/markdown",
  "embed_path": "/embeddings",
  "auth_header": "Authorization",
  "auth_prefix": "Bearer",
  "ocr_method": "GET",
  "embed_method": "POST",
  "embed_model": "bge-m3"
}
```

Never commit `config/kizuna.json`; it is gitignored because it contains secrets.

## VPS assumptions

Designed for small VPS:

- Ubuntu 22.04+
- 1 vCPU / 2GB RAM is enough for PoC
- No Docker
- No Kubernetes
- No local LLM
- No local embedding model

## Install

```bash
sudo mkdir -p /opt/rag
sudo chown -R "$USER:$USER" /opt/rag
cd /opt/rag

git clone <YOUR_REPO_URL> .

python3 -m venv venv
./venv/bin/pip install --no-cache-dir -r requirements.txt

./scripts/install_qdrant_native.sh
cp config/kizuna.example.json config/kizuna.json
# edit config/kizuna.json with your API key
```

Create Qdrant config:

```bash
cat > config/qdrant.yaml <<YAML
storage:
  storage_path: /opt/rag/storage
service:
  host: 0.0.0.0
  http_port: 6333
  grpc_port: 6334
telemetry_disabled: true
YAML
```

Install systemd services:

```bash
sudo cp systemd/qdrant-rag.service /etc/systemd/system/qdrant-rag.service
sudo cp systemd/rag-poc.service /etc/systemd/system/rag-poc.service
sudo systemctl daemon-reload
sudo systemctl enable --now qdrant-rag
sudo systemctl enable --now rag-poc
```

Verify:

```bash
curl http://127.0.0.1:6333/
curl http://127.0.0.1:8088/
systemctl status qdrant-rag rag-poc
```

Open UI:

```text
http://YOUR_SERVER_IP:8088/
```

## Kizuna APIs used

List collections:

```bash
curl -X GET "https://kizunax.io/api/v1/rag/collections" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

List documents:

```bash
curl -X GET "https://kizunax.io/api/v1/rag/documents?collection_id=COLLECTION_ID" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

Download markdown:

```bash
curl -X GET "https://kizunax.io/api/v1/rag/documents/markdown?document_id=DOCUMENT_ID" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

Generate embeddings:

```bash
curl -X POST "https://kizunax.io/api/v1/embeddings" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d input:Your text to embed
```

## UI flow

1. Configure Kizuna API settings.
2. List collections.
3. List documents in a collection.
4. Copy a document ID.
5. Fetch OCR markdown.
6. Ingest into Qdrant.
7. Use Semantic Search or Mini RAG Chat to validate retrieval.

## Chunking

Default settings in `app/main.py`:

```text
chunk_size = 800
chunk_overlap = 150
```

Metadata stored per vector:

- `document_id`
- `filename`
- `chunk_index`
- `content`

## Integrating with an AI Agent

Your agent should call this backend search flow first, then pass retrieved chunks into the LLM prompt.

Example agent prompt:

```text
Answer the user using only the retrieved context.
If the context is insufficient, say you do not know.

User question:
{{question}}

Retrieved context:
{{chunks}}
```

## Security notes

Before exposing publicly:

- Add authentication to the FastAPI UI.
- Do not expose `config/kizuna.json`.
- Prefer Cloudflare Access, VPN, or reverse proxy auth.
- Rotate API keys if accidentally committed or leaked.

## Runtime files not committed

The following are intentionally excluded:

- `config/kizuna.json`
- `venv/`
- `storage/`
- `data/`
- `bin/qdrant`
- `__pycache__/`
