# File Upload in Chat Playground — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `+` file-attach button to the Playground chat window so users can upload text files, images, PDFs, and JSON tool-definition schemas for the LLM to read.

**Architecture:** Text files and images are processed in the browser via `FileReader`. PDFs and JSON tool-definition files are POST-ed to a new `POST /api/extract` FastAPI endpoint that uses `pdfplumber` for PDFs and a TOON-stub for JSON tool schemas. On send, file contents are assembled into the OpenAI content-array format and sent alongside the user message.

**Tech Stack:** FastAPI (`UploadFile`), `pdfplumber`, React (`FileReader` API, `useState`, `useRef`), Tailwind CSS, existing Next.js proxy (`/api/*` → `localhost:4001`).

## Global Constraints

- Backend: Python 3.11+, FastAPI, existing venv at `backend/venv/`
- Frontend: Next.js 16 App Router, TypeScript, Tailwind CSS v4, `"use client"` components
- File size limit: 10 MB (enforced client-side before any read/upload)
- `/api/extract` timeout budget: 15 s (enforced client-side abort)
- All new frontend state lives in `frontend/src/app/playground/page.tsx` (no new component files — follow existing single-file pattern)
- Follow existing test pattern: `sys.path.insert(0, …)` at top, no test class wrappers

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `backend/requirements.txt` | Add `pdfplumber` |
| Modify | `backend/main.py` | Add `UploadFile`/`File` imports, `_is_tool_def()`, `_to_toon()`, `POST /api/extract` |
| Create | `backend/tests/unit/test_extract.py` | Unit tests for extraction helpers and endpoint |
| Modify | `frontend/src/app/playground/page.tsx` | All file-upload UI and logic |

---

## Task 1: Backend `/api/extract` endpoint

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/main.py`
- Create: `backend/tests/unit/test_extract.py`

**Interfaces:**
- Produces: `POST /api/extract` — accepts `multipart/form-data` field `file`, returns `{"text": str, "toon_available": bool, "toon": str | None}` on 200, `{"error": str}` on 422

---

- [ ] **Step 1: Add pdfplumber to requirements and install it**

In `backend/requirements.txt`, append after `routellm[mf]`:
```
pdfplumber
```

Then install:
```bash
cd /home/adity/StatusNeo/TAPIOD/backend
source venv/bin/activate
pip install pdfplumber
```

Expected output ends with: `Successfully installed pdfplumber-…`

---

- [ ] **Step 2: Write failing tests for `_is_tool_def` and `_to_toon`**

Create `backend/tests/unit/test_extract.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import json
import pytest
from io import BytesIO
from fastapi.testclient import TestClient


# ── helper function tests ────────────────────────────────────────────────────

def test_is_tool_def_single_object():
    from main import _is_tool_def
    assert _is_tool_def({"name": "get_weather", "parameters": {"type": "object"}}) is True

def test_is_tool_def_array():
    from main import _is_tool_def
    data = [
        {"name": "tool_a", "parameters": {}},
        {"name": "tool_b", "parameters": {}},
    ]
    assert _is_tool_def(data) is True

def test_is_tool_def_plain_json():
    from main import _is_tool_def
    assert _is_tool_def({"key": "value", "other": 123}) is False

def test_is_tool_def_array_missing_keys():
    from main import _is_tool_def
    assert _is_tool_def([{"name": "x"}]) is False  # missing "parameters"

def test_to_toon_returns_string_with_header():
    from main import _to_toon
    data = {"name": "greet", "parameters": {"type": "object", "properties": {}}}
    result = _to_toon(data)
    assert isinstance(result, str)
    assert "# TOON" in result
    assert "greet" in result

def test_to_toon_array():
    from main import _to_toon
    data = [{"name": "a", "parameters": {}}, {"name": "b", "parameters": {}}]
    result = _to_toon(data)
    assert "# TOON" in result
    assert "tool_a" in result or "a" in result


# ── endpoint tests ───────────────────────────────────────────────────────────

def test_extract_text_file():
    from main import app
    client = TestClient(app)
    content = b"def hello():\n    return 'world'\n"
    resp = client.post(
        "/api/extract",
        files={"file": ("hello.py", BytesIO(content), "text/plain")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "hello" in data["text"]
    assert data["toon_available"] is False

def test_extract_plain_json():
    from main import app
    client = TestClient(app)
    payload = json.dumps({"config": {"retries": 3}}).encode()
    resp = client.post(
        "/api/extract",
        files={"file": ("config.json", BytesIO(payload), "application/json")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "retries" in data["text"]
    assert data["toon_available"] is False

def test_extract_tool_def_json():
    from main import app
    client = TestClient(app)
    payload = json.dumps([
        {"name": "get_weather", "parameters": {"type": "object", "properties": {"city": {"type": "string"}}}},
    ]).encode()
    resp = client.post(
        "/api/extract",
        files={"file": ("tools.json", BytesIO(payload), "application/json")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["toon_available"] is True
    assert data["toon"] is not None
    assert "# TOON" in data["toon"]

def test_extract_unknown_binary_returns_422():
    from main import app
    client = TestClient(app)
    resp = client.post(
        "/api/extract",
        files={"file": ("data.bin", BytesIO(b"\x00\x01\x02\x03"), "application/octet-stream")},
    )
    assert resp.status_code == 422
```

---

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd /home/adity/StatusNeo/TAPIOD/backend
source venv/bin/activate
python -m pytest tests/unit/test_extract.py -v 2>&1 | head -40
```

Expected: multiple `ERROR` or `ImportError` lines — `_is_tool_def` and `_to_toon` and `/api/extract` don't exist yet.

---

- [ ] **Step 4: Implement helpers and endpoint in `main.py`**

At the top of `backend/main.py`, add `UploadFile` and `File` to the existing fastapi import line:

```python
# BEFORE:
from fastapi import FastAPI, Query
# AFTER:
from fastapi import FastAPI, File, Query, UploadFile
```

Add `pdfplumber` import near the top (after the existing try/except for headroom, around line 33):

```python
try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False
```

Add the two helper functions and the endpoint. Place them just before the `@app.get("/api/last_tools")` route (around line 470) to keep routes grouped:

```python
# ── /api/extract ─────────────────────────────────────────────────────────────

def _is_tool_def(data: object) -> bool:
    """Return True if data looks like an OpenAI tool-definition schema."""
    if isinstance(data, dict):
        return "name" in data and "parameters" in data
    if isinstance(data, list) and len(data) > 0:
        return all(isinstance(item, dict) and "name" in item and "parameters" in item for item in data)
    return False


def _to_toon(data: object) -> str:
    """Stub: pretty-print JSON with a # TOON header. Real converter is a drop-in replacement."""
    return "# TOON\n" + json.dumps(data, indent=2)


@app.post("/api/extract")
async def extract_file(file: UploadFile = File(...)):
    """Extract text from uploaded files. Handles PDF, JSON, text/code, and unknown binary."""
    raw = await file.read()
    mime = file.content_type or ""
    filename = file.filename or ""

    # ── PDF ──────────────────────────────────────────────────────────────────
    if mime == "application/pdf" or filename.lower().endswith(".pdf"):
        if not PDFPLUMBER_AVAILABLE:
            return JSONResponse({"error": "PDF extraction not available (pdfplumber missing)"}, status_code=422)
        try:
            import io
            with pdfplumber.open(io.BytesIO(raw)) as pdf:
                pages = [page.extract_text() or "" for page in pdf.pages]
            text = "\n\n".join(p for p in pages if p.strip())
            if not text.strip():
                return JSONResponse({"error": "PDF contained no extractable text"}, status_code=422)
            return {"text": text, "toon_available": False, "toon": None}
        except Exception as e:
            return JSONResponse({"error": f"PDF extraction failed: {type(e).__name__}"}, status_code=422)

    # ── JSON ─────────────────────────────────────────────────────────────────
    if mime in ("application/json", "text/json") or filename.lower().endswith(".json"):
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            return JSONResponse({"error": "Invalid JSON"}, status_code=422)
        if _is_tool_def(data):
            toon = _to_toon(data)
            return {"text": json.dumps(data, indent=2), "toon_available": True, "toon": toon}
        return {"text": json.dumps(data, indent=2), "toon_available": False, "toon": None}

    # ── Text / code (safety net) ──────────────────────────────────────────────
    if mime.startswith("text/"):
        try:
            return {"text": raw.decode("utf-8"), "toon_available": False, "toon": None}
        except UnicodeDecodeError:
            return JSONResponse({"error": "Could not decode file as UTF-8"}, status_code=422)

    # ── Unknown binary ────────────────────────────────────────────────────────
    return JSONResponse({"error": "Unsupported file type"}, status_code=422)
```

Also add `JSONResponse` to the fastapi.responses import:

```python
# BEFORE:
from fastapi.responses import StreamingResponse
# AFTER:
from fastapi.responses import JSONResponse, StreamingResponse
```

---

- [ ] **Step 5: Run tests and verify they pass**

```bash
cd /home/adity/StatusNeo/TAPIOD/backend
source venv/bin/activate
python -m pytest tests/unit/test_extract.py -v
```

Expected: all 10 tests `PASSED`.

---

- [ ] **Step 6: Commit**

```bash
cd /home/adity/StatusNeo/TAPIOD
git add backend/requirements.txt backend/main.py backend/tests/unit/test_extract.py
git commit -m "feat: add POST /api/extract endpoint for file text extraction"
```

---

## Task 2: Frontend file data model and processing logic

**Files:**
- Modify: `frontend/src/app/playground/page.tsx`

**Interfaces:**
- Consumes: `POST /api/extract` → `{text, toon_available, toon}` (from Task 1)
- Produces: `AttachedFile[]` state, `buildContent(text, files)` → `string | MessageContentPart[]`, `processFile(file)` → `void`

---

- [ ] **Step 1: Add new interfaces and update `Message`**

In `frontend/src/app/playground/page.tsx`, find the existing interfaces at the top and add/update:

```typescript
// Add after the existing PipelineStep interface:

interface MessageContentPart {
  type: "text" | "image_url";
  text?: string;
  image_url?: { url: string };
}

interface AttachedFile {
  id: string;
  name: string;
  mimeType: string;
  status: "ready" | "loading" | "error";
  text?: string;
  base64?: string;
  toonAvailable?: boolean;
  toon?: string;
  useToon?: boolean;
  errorMsg?: string;
}
```

Update the existing `Message` interface:

```typescript
// BEFORE:
interface Message {
  role: "user" | "assistant";
  content: string;
}
// AFTER:
interface Message {
  role: "user" | "assistant";
  content: string | MessageContentPart[];
}
```

---

- [ ] **Step 2: Add constants for vision-model detection**

After the existing `LAYER_LABELS` constant, add:

```typescript
const GROQ_MODELS = new Set(["heavy-groq", "fast-groq"]);

const FILE_ICON: Record<string, string> = {
  "image/png": "🖼",
  "image/jpeg": "🖼",
  "image/webp": "🖼",
  "image/gif": "🖼",
  "application/pdf": "📕",
  "application/json": "📋",
  "text/plain": "📄",
};
function fileIcon(mime: string, name: string): string {
  if (FILE_ICON[mime]) return FILE_ICON[mime];
  if (mime.startsWith("image/")) return "🖼";
  if (mime.startsWith("text/")) return "📄";
  const ext = name.split(".").pop()?.toLowerCase();
  if (ext === "pdf") return "📕";
  if (ext === "json") return "📋";
  return "📎";
}
```

---

- [ ] **Step 3: Add state and refs inside the `Playground` component**

Inside `export default function Playground()`, after the existing `const bottomRef = useRef(...)` line, add:

```typescript
const [attachedFiles, setAttachedFiles] = useState<AttachedFile[]>([]);
const [oneOffModel, setOneOffModel] = useState<string | null>(null);
const fileInputRef = useRef<HTMLInputElement>(null);
const baseModel = "heavy-groq";
```

---

- [ ] **Step 4: Add helper functions inside the component**

Add these two functions inside `Playground`, after `formatTime` and before `return (`:

```typescript
function getDisplayText(content: string | MessageContentPart[]): string {
  if (typeof content === "string") return content;
  return content
    .filter(p => p.type === "text")
    .map(p => p.text ?? "")
    .join("\n");
}

function buildContent(
  userText: string,
  files: AttachedFile[]
): string | MessageContentPart[] {
  const ready = files.filter(f => f.status === "ready");
  const textFiles = ready.filter(f => f.text !== undefined);
  const imageFiles = ready.filter(f => f.base64 !== undefined);

  if (ready.length === 0) return userText;

  if (imageFiles.length === 0) {
    // Text-only attachments: prepend as a single string
    const prefix = textFiles
      .map(f => `${f.name}\n---\n${(f.useToon && f.toon) ? f.toon : f.text!}`)
      .join("\n\n");
    return prefix ? `${prefix}\n\n${userText}` : userText;
  }

  // Images present — must use content array
  const parts: MessageContentPart[] = [];
  textFiles.forEach(f => {
    parts.push({
      type: "text",
      text: `${f.name}\n---\n${(f.useToon && f.toon) ? f.toon : f.text!}`,
    });
  });
  imageFiles.forEach(f => {
    parts.push({ type: "image_url", image_url: { url: f.base64! } });
  });
  if (userText.trim()) {
    parts.push({ type: "text", text: userText });
  }
  return parts;
}
```

---

- [ ] **Step 5: Add the `processFile` function inside the component**

Add after `buildContent`, still before `return (`:

```typescript
const processFile = async (file: File): Promise<void> => {
  if (file.size > 10 * 1024 * 1024) {
    // Reject client-side — chip never appears
    console.warn(`[TAPIOD] File ${file.name} exceeds 10 MB limit`);
    return;
  }

  const id = Math.random().toString(36).slice(2, 10);
  const mimeType = file.type || "application/octet-stream";
  const stub: AttachedFile = { id, name: file.name, mimeType, status: "loading" };
  setAttachedFiles(prev => [...prev, stub]);

  const setReady = (patch: Partial<AttachedFile>) =>
    setAttachedFiles(prev => prev.map(f => f.id === id ? { ...f, status: "ready", ...patch } : f));
  const setError = (errorMsg: string) =>
    setAttachedFiles(prev => prev.map(f => f.id === id ? { ...f, status: "error", errorMsg } : f));

  // ── Images ────────────────────────────────────────────────────────────────
  if (mimeType.startsWith("image/")) {
    const reader = new FileReader();
    reader.onload = () => setReady({ base64: reader.result as string });
    reader.onerror = () => setError("Could not read image");
    reader.readAsDataURL(file);
    return;
  }

  // ── JSON — check client-side for tool-def shape ───────────────────────────
  if (mimeType === "application/json" || file.name.toLowerCase().endsWith(".json")) {
    const reader = new FileReader();
    reader.onload = async () => {
      const raw = reader.result as string;
      let parsed: unknown;
      try { parsed = JSON.parse(raw); } catch { setReady({ text: raw }); return; }
      const isTool =
        (typeof parsed === "object" && parsed !== null && !Array.isArray(parsed) &&
         "name" in (parsed as object) && "parameters" in (parsed as object)) ||
        (Array.isArray(parsed) && parsed.length > 0 &&
         (parsed as any[]).every((item: any) => "name" in item && "parameters" in item));

      if (!isTool) { setReady({ text: JSON.stringify(parsed, null, 2) }); return; }

      // Tool-def: send to /api/extract for TOON
      try {
        const fd = new FormData();
        fd.append("file", file);
        const res = await fetch("/api/extract", { method: "POST", body: fd, signal: AbortSignal.timeout(15000) });
        if (!res.ok) { const e = await res.json(); setError(e.error ?? "Extraction failed"); return; }
        const data = await res.json();
        setReady({ text: data.text, toonAvailable: data.toon_available, toon: data.toon ?? undefined });
      } catch (e: any) {
        setError(e?.name === "TimeoutError" ? "Extraction timed out" : "Extraction failed");
      }
    };
    reader.onerror = () => setError("Could not read file");
    reader.readAsText(file);
    return;
  }

  // ── Plain text / code ─────────────────────────────────────────────────────
  if (mimeType.startsWith("text/")) {
    const reader = new FileReader();
    reader.onload = () => setReady({ text: reader.result as string });
    reader.onerror = () => setError("Could not read file");
    reader.readAsText(file);
    return;
  }

  // ── PDF and everything else → backend ────────────────────────────────────
  try {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch("/api/extract", { method: "POST", body: fd, signal: AbortSignal.timeout(15000) });
    if (!res.ok) { const e = await res.json(); setError(e.error ?? "Extraction failed"); return; }
    const data = await res.json();
    setReady({ text: data.text, toonAvailable: data.toon_available, toon: data.toon ?? undefined });
  } catch (e: any) {
    setError(e?.name === "TimeoutError" ? "Extraction timed out" : "Extraction failed");
  }
};
```

---

- [ ] **Step 6: Update `sendMessage` to assemble content and clear files after send**

Find the existing `sendMessage` function. Replace the relevant lines:

```typescript
// BEFORE (inside sendMessage, the try block start):
  try {
    const res = await fetch("/api/agent/chat/completions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: "heavy-groq",
        messages: newMessages.map(m => ({ role: m.role, content: m.content })),
        user: USER_ID,
        metadata: { session_id: currentSessionId },
      }),
    });

// AFTER:
  const modelToUse = oneOffModel ?? baseModel;
  setOneOffModel(null);

  try {
    const res = await fetch("/api/agent/chat/completions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: modelToUse,
        messages: newMessages.map(m => ({ role: m.role, content: m.content })),
        user: USER_ID,
        metadata: { session_id: currentSessionId },
      }),
    });
```

Also, the user message created in `sendMessage` needs to use `buildContent`. Find and replace:

```typescript
// BEFORE:
    const userMsg: Message = { role: "user", content: input };
    const newMessages = [...messages, userMsg];
    setMessages(newMessages);
    setInput("");

// AFTER:
    const assembled = buildContent(input, attachedFiles);
    const userMsg: Message = { role: "user", content: assembled };
    const newMessages = [...messages, userMsg];
    setMessages(newMessages);
    setInput("");
    setAttachedFiles([]);
```

Also update `regenerate` to use `baseModel` instead of the hardcoded string:

```typescript
// BEFORE (inside regenerate):
        body: JSON.stringify({
          model: "heavy-groq",
// AFTER:
        body: JSON.stringify({
          model: baseModel,
```

---

- [ ] **Step 7: Update message display to use `getDisplayText`**

Find where messages are rendered (around line 264 in original). Replace `{m.content}` with `{getDisplayText(m.content)}`:

```typescript
// BEFORE:
                <p className="text-[var(--text-primary)] whitespace-pre-wrap">{m.content}</p>
// AFTER:
                <p className="text-[var(--text-primary)] whitespace-pre-wrap">{getDisplayText(m.content)}</p>
```

---

- [ ] **Step 8: Run TypeScript check to verify no type errors**

```bash
cd /home/adity/StatusNeo/TAPIOD/frontend
npm run lint 2>&1 | tail -20
```

Expected: no errors relating to `Message`, `AttachedFile`, or `MessageContentPart`.

---

- [ ] **Step 9: Commit**

```bash
cd /home/adity/StatusNeo/TAPIOD
git add frontend/src/app/playground/page.tsx
git commit -m "feat: add file attachment data model and processing logic to playground"
```

---

## Task 3: Frontend UI — chips, `+` button, hidden input, vision warning

**Files:**
- Modify: `frontend/src/app/playground/page.tsx`

**Interfaces:**
- Consumes: `attachedFiles` state, `processFile()`, `setAttachedFiles()`, `oneOffModel`, `setOneOffModel()` (from Task 2)

---

- [ ] **Step 1: Add the hidden file input and `+` button to the input bar**

Find the existing input bar div (around line 289 in original, the `<div className="flex gap-2">` that wraps the input and Send button). Replace it:

```typescript
// BEFORE:
        <div className="flex gap-2">
          <input
            ref={inputRef}
            className="flex-1 bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-purple-light)]"
            placeholder="Type a message…"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === "Enter" && sendMessage()}
          />
          <button
            onClick={sendMessage}
            disabled={loading}
            className="px-4 py-2 rounded-lg bg-[var(--accent-purple)] text-white text-sm font-medium disabled:opacity-50"
          >
            Send
          </button>
        </div>

// AFTER:
        {/* File chips row */}
        {attachedFiles.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-2">
            {attachedFiles.map(f => (
              <div
                key={f.id}
                className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs border transition-colors ${
                  f.status === "error"
                    ? "bg-red-500/10 border-red-500/30 text-red-400"
                    : f.status === "loading"
                    ? "bg-white/5 border-white/10 text-[var(--text-muted)]"
                    : "bg-white/8 border-white/15 text-[var(--text-primary)]"
                }`}
              >
                <span>{f.status === "loading" ? "⏳" : fileIcon(f.mimeType, f.name)}</span>
                <span className="max-w-[120px] truncate">
                  {f.name.length > 20 ? f.name.slice(0, 18) + "…" : f.name}
                </span>
                {f.status === "error" && (
                  <span className="text-[10px] opacity-70 max-w-[80px] truncate">{f.errorMsg}</span>
                )}
                {f.status === "ready" && f.toonAvailable && (
                  <button
                    onClick={() =>
                      setAttachedFiles(prev =>
                        prev.map(a => a.id === f.id ? { ...a, useToon: !a.useToon } : a)
                      )
                    }
                    className={`px-1 rounded text-[9px] font-mono border transition-colors ${
                      f.useToon
                        ? "bg-[var(--accent-purple)]/30 border-[var(--accent-purple)]/50 text-[var(--accent-purple-light)]"
                        : "border-white/20 text-[var(--text-muted)] hover:border-white/40"
                    }`}
                  >
                    {f.useToon ? "TOON ✓" : "→ TOON"}
                  </button>
                )}
                {f.status !== "loading" && (
                  <button
                    onClick={() => setAttachedFiles(prev => prev.filter(a => a.id !== f.id))}
                    className="text-[var(--text-muted)] hover:text-red-400 transition-colors ml-0.5"
                  >
                    ✕
                  </button>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Input row */}
        <div className="flex gap-2">
          {/* Hidden file input */}
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".txt,.md,.py,.js,.ts,.jsx,.tsx,.json,.csv,.yaml,.yml,.html,.css,.pdf,.png,.jpg,.jpeg,.webp,.gif"
            className="hidden"
            onChange={e => {
              Array.from(e.target.files ?? []).forEach(processFile);
              e.target.value = "";
            }}
          />
          {/* + button */}
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={loading}
            className="px-3 py-2 rounded-lg border border-white/10 text-[var(--text-muted)] text-sm hover:border-white/20 hover:text-[var(--text-primary)] disabled:opacity-40 transition-colors"
            title="Attach file"
          >
            +
          </button>
          <input
            ref={inputRef}
            className="flex-1 bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-purple-light)]"
            placeholder="Type a message…"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === "Enter" && sendMessage()}
          />
          <button
            onClick={sendMessage}
            disabled={loading || attachedFiles.some(f => f.status === "loading")}
            className="px-4 py-2 rounded-lg bg-[var(--accent-purple)] text-white text-sm font-medium disabled:opacity-50"
          >
            Send
          </button>
        </div>
```

---

- [ ] **Step 2: Add the vision-model warning banner**

Add the warning banner just above the chips row (still inside the chat panel, just before the `{attachedFiles.length > 0 &&` block added in Step 1):

```typescript
        {/* Vision warning banner */}
        {attachedFiles.some(f => f.status === "ready" && f.base64) && GROQ_MODELS.has(oneOffModel ?? baseModel) && (
          <div className="flex items-center justify-between gap-3 mb-2 px-3 py-2 rounded-lg bg-amber-500/10 border border-amber-500/20 text-xs">
            <span className="text-amber-300">⚠ Groq/Llama doesn't support images.</span>
            <div className="flex gap-2 shrink-0">
              <button
                onClick={() => setOneOffModel("heavy-openai")}
                className="px-2 py-1 rounded bg-amber-500/20 border border-amber-500/30 text-amber-200 hover:bg-amber-500/30 transition-colors"
              >
                Use gpt-4o for this message
              </button>
              <button
                onClick={() => setAttachedFiles(prev => prev.filter(f => !f.base64))}
                className="px-2 py-1 rounded border border-white/10 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
              >
                Remove images
              </button>
            </div>
          </div>
        )}
```

---

- [ ] **Step 3: Run the frontend dev server and verify visually**

```bash
cd /home/adity/StatusNeo/TAPIOD/frontend
npm run dev
```

Open `http://localhost:3000/playground` and verify:
1. A `+` button appears left of the text input
2. Clicking `+` opens the OS file picker
3. Attaching a `.py` file shows a `📄 filename.py ✕` chip immediately
4. Attaching a `.pdf` shows a `⏳ report.pdf` chip that resolves to `📕 report.pdf ✕`
5. Attaching a `tools.json` with `[{"name":"x","parameters":{}}]` shape shows `📋 tools.json → TOON ✕` chip; clicking `→ TOON` changes badge to `TOON ✓`
6. Attaching an image with Groq active shows the amber warning banner with both action buttons
7. Clicking "Remove images" clears image chips and hides the banner
8. Send button is disabled while any chip is in loading state
9. After send, chips are cleared

---

- [ ] **Step 4: Run lint**

```bash
cd /home/adity/StatusNeo/TAPIOD/frontend
npm run lint 2>&1 | tail -10
```

Expected: `✔ No ESLint warnings or errors`

---

- [ ] **Step 5: Commit**

```bash
cd /home/adity/StatusNeo/TAPIOD
git add frontend/src/app/playground/page.tsx
git commit -m "feat: add file attachment chips, + button, and vision warning to playground"
```

---

## Verification Checklist (end-to-end)

Run backend and frontend, then manually verify each item from the spec:

1. Attach a `.py` file → chip appears → Send → LLM response references the code content
2. Attach a `.pdf` → chip spins → resolves → Send → LLM response references PDF content
3. Attach a JSON tool-definition → chip shows `→ TOON` badge → toggle → Send → check browser DevTools Network tab: request body `content` contains `# TOON` header
4. Attach a `.png` with Groq active → amber warning banner; click "Use gpt-4o for this message" → request goes out with `model: "heavy-openai"`; next message uses `heavy-groq` again
5. Attach a `.png` with model already `heavy-openai` → no warning, Send succeeds
6. Attach a file >10MB → chip never appears (check console for `[TAPIOD] File … exceeds 10 MB`)
7. Remove a chip via `✕` → file absent from send payload
