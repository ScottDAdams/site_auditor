# Site Auditor

A small FastAPI pipeline that crawls sites, embeds page text, clusters similar pages, and reports likely duplicates.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Set `OPENAI_API_KEY` in your environment for embeddings.

## Run

From the project root:

```bash
uvicorn app.main:app --reload
```

Open [http://localhost:8000](http://localhost:8000).

Enter comma-separated URLs (include `https://` where needed for the crawler).
