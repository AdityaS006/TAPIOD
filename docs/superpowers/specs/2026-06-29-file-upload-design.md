# File Upload in Chat Playground

**Date:** 2026-06-29  
**Status:** Approved

## Context

The Playground chat window (`frontend/src/app/playground/page.tsx`) currently accepts only text input. Users need to attach files — code, documents, images, JSON tool schemas — so the LLM can reason over them. A future TOON format will allow JSON tool-definition files to be compressed before injection, saving tokens.

---

## Approach

Hybrid (Approach C): text files and images are processed entirely in the browser; PDFs and unknown binary formats are sent to a new backend `/api/extract` endpoint. JSON files with tool-definition shapes also go through `/api/extract` for TOON detection/conversion.

---

## Data Model

```ts
interface AttachedFile {
  id: string            // random key for React list
  name: string          // original filename
  mimeType: string      // e.g. "image/png", "application/pdf", "text/plain"
  status: "ready" | "loading" | "error"
  text?: string         // extracted text (text files, PDFs, JSON)
  base64?: string       // data URL for images ("data:image/png;base64,...")
  toonAvailable?: boolean  // true when file is a JSON tool-definition schema
  toon?: string            // TOON-converted representation (when available)
  useToon?: boolean        // user toggle: send as TOON vs raw JSON
  errorMsg?: string     // populated when status === "error"
}
```

---

## Backend: `POST /api/extract`

**New endpoint in `backend/main.py`.**

```
POST /api/extract
Content-Type: multipart/form-data
Field: file

200 OK  →  { "text": "...", "toon_available": false }
200 OK  →  { "text": "...", "toon_available": true, "toon": "..." }   (JSON tool defs)
422     →  { "error": "Could not extract text from this file" }
```

**Extraction logic by file type:**

| File type | Handler |
|-----------|---------|
| `.pdf` | `pdfplumber` — extract all pages, join with `\n\n` |
| `.json` | Parse, detect tool-def shape (`name` + `parameters` keys present at top level or in array). If matched: set `toon_available: true`, populate `toon` via `_to_toon()` stub. Otherwise: pretty-print JSON as text. |
| Text / code (fallback) | Read as UTF-8 (browser normally handles these; backend is a safety net) |
| Unknown binary | Return 422 |

**Tool-def detection:** a JSON file is considered a tool definition if the top-level value is either:
- An object with both `"name"` and `"parameters"` keys, or
- An array where every element has `"name"` and `"parameters"` keys.

**TOON stub (`_to_toon()`):** for now returns the JSON pretty-printed with a `# TOON` comment header. Real conversion is a drop-in replacement when the TOON module is ready.

**New dependency:** `pdfplumber` — add to `backend/requirements.txt`.

---

## Frontend: `frontend/src/app/playground/page.tsx`

### Input bar

```
[ + ] [ text input ................................ ] [ Send ]
```

- `+` button triggers a hidden `<input type="file" multiple accept="...">`.  
- Accepted extensions: `.txt .md .py .js .ts .jsx .tsx .json .csv .yaml .yml .html .css .pdf .png .jpg .jpeg .webp .gif` (plus any extension-less files routed to `/api/extract`).

### Chips (above input bar, when files attached)

```
[ 📄 schema.json → TOON ✕ ]  [ 🖼 shot.png ✕ ]  [ ⏳ report.pdf ]
```

- Spinner while PDF / JSON is in-flight to `/api/extract`.
- Red chip + truncated error message on failure.
- `→ TOON` badge on JSON tool-def files; clicking toggles `useToon` (sends TOON text instead of raw JSON).
- `✕` removes the file from state.

### Vision-model warning banner

Shown above the chips when **images are attached** and the active model is Groq (llama):

```
⚠ Groq/Llama doesn't support images.
  [ Use gpt-4o for this message ]   [ Remove images ]
```

- "Use gpt-4o for this message": stores original model in a `ref`, sends this one request with `heavy-openai`, restores on next send.
- "Remove images": filters image files from `attachedFiles`.
- Vision-capable models: `heavy-openai`, `fast-openai`, `heavy-anthropic`, `fast-anthropic`, `heavy-gemini`, `fast-gemini`.
- Groq models (non-vision): `heavy-groq`, `fast-groq`.

### File processing on attach (per type)

| Category | Mime / extension | Processing |
|----------|-----------------|------------|
| Text / code | `text/*`, `.json`, `.yaml`, `.csv`, `.md`, `.py`, etc. | `FileReader.readAsText()` → `text` |
| Images | `image/png`, `image/jpeg`, `image/webp`, `image/gif` | `FileReader.readAsDataURL()` → `base64` |
| PDF | `application/pdf` | POST to `/api/extract` → `text` |
| JSON (tool-def) | `application/json` + tool-def shape | POST to `/api/extract` → `text` + optional `toon` |
| Everything else | any binary | POST to `/api/extract` → `text` or error |

JSON files are first tried via `FileReader.readAsText()` and parsed client-side to detect tool-def shape. If detected, they are re-sent to `/api/extract` for TOON processing. Non-tool-def JSON stays client-side.

### Message assembly on send

| Attachments | `content` format sent to API |
|-------------|------------------------------|
| None | `string` (unchanged, no regression) |
| Text/PDF/JSON only | Single `{type:"text"}` block: file blocks prepended (`<filename>\n---\n<content>\n\n`), then user message |
| Images only | Content array: `{type:"image_url", image_url:{url:"data:..."}}` per image, then `{type:"text", text: userMessage}` |
| Mixed | Text blocks first, then image blocks, then user text block |

Messages stored in session history use the same assembled format so past image messages round-trip correctly when reloading a session.

---

## Error Handling

- `/api/extract` timeout (>15s): chip turns red, error message "Extraction timed out".
- `/api/extract` 422: chip turns red, shows server error message.
- File too large (>10MB): rejected client-side before any read/upload, chip never appears.
- FileReader error: chip turns red with browser error message.

---

## Out of Scope (this iteration)

- TOON full conversion logic (stub only; real converter is a future drop-in).
- Drag-and-drop onto the chat window (can be added later without architectural changes).
- Multi-file paste from clipboard.
- File preview modal on chip click.

---

## Verification

1. Attach a `.py` file → chip appears, send → LLM response references the code.
2. Attach a `.pdf` → chip shows spinner, resolves, send → LLM response references the PDF content.
3. Attach a JSON tool-definition → chip shows `→ TOON` badge, toggle it, send → message payload contains TOON text.
4. Attach a `.png` with Groq active → warning banner appears; click "Use gpt-4o for this message" → request succeeds with gpt-4o; next message reverts to Groq.
5. Attach a `.png` with OpenAI active → no warning, send succeeds.
6. Attach a file >10MB → chip never appears, console/UI error shown.
7. Remove a chip → file removed from payload, send works without it.
