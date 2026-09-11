# Playground Template

A Next.js template with [Plate](https://platejs.org/) AI, plugins and components.

## Features

- Next.js 16
- [Plate](https://platejs.org/) editor
- [shadcn/ui](https://ui.shadcn.com/)
- [MCP](https://platejs.org/docs/components/mcp)
- Python backend (`backend/`) for document storage and the AI endpoints

## Requirements

- Node.js 20+
- bun
- uv / Python 3.13 (for the backend)

## Installation

Choose one of these methods:

### 1. Using CLI (Recommended)

```bash
npx shadcn@latest add @plate/editor-ai
```

### 2. Using Template

[Use this template](https://github.com/udecode/plate-playground-template/generate), then install dependencies:

```bash
bun install
```

## Development

Copy the example env file:

```bash
cp .env.example .env.local
```

Configure `.env.local`:

- `UPLOADTHING_TOKEN` – UploadThing API key ([get one here](https://uploadthing.com/dashboard))
- `NEXT_PUBLIC_BACKEND_URL` – base URL of the Python backend (default `http://localhost:8000`)

## Backend

Documents and the AI endpoints (`/api/ai/command`, `/api/ai/copilot`) live in the
Python FastAPI backend. Slate content is stored as JSON in `backend/data/docs/`; the
AI chat/copilot use [LiveKit Agents](https://docs.livekit.io/agents) with an
OpenAI-compatible provider.

```bash
cd backend
uv venv .venv && uv pip install -p .venv -r requirements.txt
cp .env.example .env        # set OPENAI_API_KEY (optional base URL/model overrides)
.venv/bin/uvicorn app.main:app --reload --port 8000
```

When `OPENAI_API_KEY` is set it wins; otherwise the key entered in the editor
settings is used. The AI command context (markdown/block ids/selection) is
serialized client-side in `src/lib/ai-command-context.ts`.

## Development

Copy the example env file:

```bash
cp .env.example .env.local
```

Enter your own [AI Gateway key](https://vercel.com/ai-gateway) in the editor settings to use AI. The example API routes use the caller's key.
The live path for chat and copilot is the Python backend; the Next.js routes under
`src/app/api/ai/` are kept as an AI-gateway fallback reference.

Uploads work in local development. Before enabling production uploads, replace the development check in `src/lib/uploadthing.ts` with your application's session and permission checks. Add per-user upload limits.

If your application uses a shared server AI credential, authorize each request and enforce per-user usage limits before calling the provider. Keep server credentials out of client code.

Start the development server:

```bash
bun dev
```

Visit http://localhost:3000/editor to see the editor in action.
