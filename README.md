# SchemeKnit

AI-assisted lesson plan generator for Ghanaian schools. Upload your scheme of work, review curriculum alignment, allocate indicators to teaching periods, and generate full lesson plans — DOCX, PDF, XLSX, and ZIP exports.

## Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌──────────────┐
│  Frontend    │────▶│  FastAPI Backend  │────▶│  PostgreSQL   │
│  (Next.js)  │     │  (Python)        │     │  (Neon)       │
└─────────────┘     └──────────────────┘     └──────────────┘
                           │                        │
                    ┌──────┴──────┐          ┌──────┴──────┐
                    │  R2 Storage │          │  AI Provider│
                    │ (Cloudflare)│          │ (OpenCode   │
                    └─────────────┘          │  Zen)       │
                                             └─────────────┘
```

- **Frontend**: Next.js 14, React 18, Tailwind CSS, Radix UI
- **Backend**: FastAPI 0.141, SQLAlchemy 2.0, Python 3.11
- **Database**: PostgreSQL (Neon serverless)
- **Storage**: Cloudflare R2 (S3-compatible)
- **Email**: Resend (transactional)
- **AI**: OpenCode Zen (free tier — Nemotron 3 Ultra Free, MiMo V2.5 Free)
- **PDF Export**: LibreOffice headless (desktop) / pymupdf (web)

## Local Development

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env — set DEBUG=true for local dev
python -m uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:3000
```

### Desktop

```bash
cd desktop
npm install
# Build backend: python package_backend.py
# Build EXE: build.bat (requires NSIS)
```

## Environment Variables

See `backend/.env.example` for the full list. Key variables:

| Variable | Purpose | Required |
|----------|---------|----------|
| `DATABASE_URL` | PostgreSQL connection string | Production |
| `SECRET_KEY` | Session signing secret | Production |
| `JWT_SECRET_KEY` | JWT signing secret | Production |
| `STORAGE_BACKEND` | `local` or `s3` | Production |
| `S3_ENDPOINT` | R2/S3 endpoint URL | When STORAGE_BACKEND=s3 |
| `S3_BUCKET` | Object storage bucket | When STORAGE_BACKEND=s3 |
| `RESEND_API_KEY` | Resend email API key | Production |
| `AI_MODE` | `OFF`, `opencode-zen`, `ollama`, etc. | Optional |
| `PLATFORM_ADMIN_BOOTSTRAP_SECRET` | One-time bootstrap secret | First deploy |
| `PREVIEW_MODE` | Allow resend.dev test sender | Preview builds |

## Deployment

### Web (Render Free)

- **Frontend**: `cd frontend && npm install && npm run build:web` → `npx next start -p $PORT`
- **Backend**: `cd backend && pip install -r requirements.txt` → `uvicorn src.main:app --host 0.0.0.0 --port $PORT`
- Python 3.11 (see `.python-version`)
- PostgreSQL via Neon (free tier)
- File storage via Cloudflare R2 (free tier)
- AI via OpenCode Zen free models

### Desktop (Windows)

- Local-first, offline-capable
- SQLite database
- Bundled LibreOffice for PDF export
- Self-contained installer (~500 MB)

## Roles

| Role | Platform | Capabilities |
|------|----------|-------------|
| Platform Admin | Web only | Manage schools, licenses, activation codes, platform settings |
| School Admin | Web + Desktop | Manage teachers, upload schemes, generate lessons |
| Teacher | Web + Desktop | Upload schemes, generate personal lesson plans |
| Individual Teacher | Web only | Standalone teacher without school affiliation |

## Version

Current: **1.0.5**

## License

Proprietary — SchemeKnit. All rights reserved.
