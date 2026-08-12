# AI Content Generator + SEO Blog

Full-stack portfolio project demonstrating AI-assisted drafting and SEO workflow patterns.

> **Status:** engineering demo. Generated content and SEO scores are suggestions, not guarantees of accuracy, originality, ranking or compliance.

## Stack

```text
Frontend   Next.js 14 + TypeScript + Tailwind CSS
Backend    FastAPI + SQLAlchemy + Pydantic
Database   SQLite locally / PostgreSQL-ready
AI         Optional provider integration
```

## Demonstrated features

- topic-to-draft content workflow;
- metadata / SEO suggestion patterns;
- blog list and detail pages;
- JWT authentication;
- provider integration points.

## Local setup

Backend:

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## Production requirements

Keep AI provider keys on the backend, rate-limit generation, validate user input, moderate where required, preserve source/citation information when research is involved and require human review before publishing important content.

Never expose an OpenAI/Gemini/provider secret through `NEXT_PUBLIC_*` or other browser variables.

## Author

Rajiv Kapur — Software Architect & Full-Stack Developer

Portfolio: `https://rajivkapur.in.net`
