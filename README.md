# User Profiler API

A FastAPI service for managing rich user profiles on a property graph, backed by [Grafeo](https://grafeo.dev). Each profile maps onto the PG-schema defined in `schema/user_model.pg` and captures identity, location, ORCID research output, session activity, and session-extracted keywords.

A Streamlit web UI (`app.py`) is included for interactive use.

---

## Project structure

```
user_profiler/
├── up_api/
│   ├── main.py                   # FastAPI app and all endpoints
│   └── resources/
│       ├── data_models.py        # Pydantic models (node types + request bodies)
│       ├── graph_helpers.py      # GQL utilities and graph CRUD operations
│       ├── orcid_helpers.py      # ORCID public API client
│       ├── LLM_helpers.py        # LLM keyword generation
│       └── profile_helpers.py    # Portable interest-profile shaping
├── examples/
│   ├── api_examples.sh           # curl examples (bash)
│   └── api_examples.ps1          # Invoke-RestMethod examples (PowerShell)
├── schema/
│   └── user_model.pg             # PG-schema definition
├── app.py                        # Streamlit web UI
└── requirements.txt
```

---

## Data model

```
User ──HAS_SESSION_KEYWORD──► Keyword          (session-extracted keywords)
     ──HAS_LOCATION─────────► Location
     ──HAS_ORCID────────────► ORCID ──HAS_KEYWORD─────► Keyword   (ORCID research keywords)
                                    ──HAS_PUBLICATION──► Publication ──HAS_AUTHOR──► Author
     ──HAS_SESSION──────────► Session ──HAS_QUERY──► Query
```

`User.keywords` (via `HAS_SESSION_KEYWORD`) stores keywords generated from the user's chat sessions and is independent of the ORCID profile.

### Keyword ageing

Session keywords carry two timestamps: `addedAt` (first saved) and `lastSeenAt` (last time the LLM extracted them). Their **weight** decays with the time since `lastSeenAt`: 1.0 when just seen, halving every `KEYWORD_HALF_LIFE_DAYS`. Re-extracting a keyword refreshes it back to 1.0, so recurring interests stay strong. ORCID keywords have no timestamps and get the constant `ORCID_KEYWORD_WEIGHT`.

Keywords whose weight drops below `KEYWORD_MIN_WEIGHT` **expire**. They stay in the graph and in `GET /user/{id}`, but `GET /user/{id}/profile` stops returning them, so other services no longer use them. Extracting them again brings them back.

| Variable | Default | Meaning |
|---|---|---|
| `KEYWORD_HALF_LIFE_DAYS` | `30` | Days for a session keyword's weight to halve |
| `KEYWORD_MIN_WEIGHT` | `0.1` | Below this weight a keyword expires (about 100 days with the default half-life) |
| `ORCID_KEYWORD_WEIGHT` | `0.5` | Constant weight of ORCID keywords |

Keywords saved before timestamps existed are stamped the next time the user's profile is saved (any edit, including new chat messages).

---

## Setup

**Requirements:** Python 3.12+

```bash
pip install -r requirements.txt
```

### Environment variables

The LLM keyword generation endpoint requires two environment variables:

| Variable | Description |
|---|---|
| `LLM_TOKEN` | Bearer token for the LLM API |
| `LLM_API_URL` | Full URL of the LLM chat completions endpoint |
| `LLM_SSL_VERIFY` | Optional. TLS certificate verification for the LLM API. `true` (default) uses the system CAs, a file path uses that CA bundle or certificate, `false` disables verification (e.g. for an endpoint with a self-signed certificate). |
| `DMM_URL` | Optional. Base URL of the DMM, where keyword generation reads the user's query history (with the caller's token). Defaults to `https://datagems-dev.scayle.es/dmm`. If the DMM is unreachable or returns an error other than 404, keyword generation answers 502. |

Set them **before** starting the server (they are read once at startup):

```bash
# bash
export LLM_TOKEN="your-token"
export LLM_API_URL="https://your-llm-host/v1/chat/completions"

# PowerShell
$env:LLM_TOKEN = "your-token"
$env:LLM_API_URL = "https://your-llm-host/v1/chat/completions"
```

The internal LLM endpoint (`https://172.16.59.5:32443`) uses a self-signed certificate, so locally you also need `LLM_SSL_VERIFY`. Otherwise keyword generation fails with `CERTIFICATE_VERIFY_FAILED`. Either trust that certificate (recommended) or disable verification:

```bash
# bash: save the endpoint's certificate once and verify against it
openssl s_client -connect 172.16.59.5:32443 </dev/null 2>/dev/null | openssl x509 > scayle-llm.pem
export LLM_SSL_VERIFY="$PWD/scayle-llm.pem"      # or: export LLM_SSL_VERIFY=false

# PowerShell
$env:LLM_SSL_VERIFY = "C:\path\to\scayle-llm.pem"   # or: $env:LLM_SSL_VERIFY = "false"
```

If these are not set, all other endpoints still work; only `GET /user/{id}/generate-keywords` will return an error.

---

## Running

All commands should be run from the project root (`user_profiler/`).

### 1. User Profiler API (required)

```bash
uvicorn up_api.main:app --reload
```

Runs on **http://localhost:8000**. Interactive docs: **http://localhost:8000/docs**

### 2. Streamlit UI (optional)

```bash
streamlit run app.py
```

The UI will not start if the User Profiler API is not reachable.

---

## Endpoints

### `GET /users` — List all users

```bash
curl http://localhost:8000/users
```

```json
{
  "count": 2,
  "users": [
    { "userId": "3f2e1d4c-...", "name": "Alice", "surname": "Rossi" },
    { "userId": "a1b2c3d4-...", "name": "Bob",   "surname": "Verdi" }
  ]
}
```

---

### `GET /user/{user_id}` — Retrieve a user

Returns the full profile, or HTTP 404 with `{"detail": "No such user: '...'"}` if not found. The same 404 applies to every `/user/{user_id}` endpoint below.

```bash
curl http://localhost:8000/user/3f2e1d4c-...
```

```json
{
  "userId": "3f2e1d4c-...",
  "name": "Alice",
  "surname": "Rossi",
  "age": 34,
  "email": "alice.rossi@example.com",
  "affiliation": "University of Milan",
  "keywords": [],
  "location": null,
  "orcid": null,
  "sessions": []
}
```

---

### `GET /user/{user_id}/profile` — Retrieve a portable interest profile

Returns a trimmed, generic profile meant for consumption by other services on the platform, rather than the full internal representation returned by `GET /user/{user_id}`. It drops PII (`email`, `dateOfBirth`) and the raw session/query log, and merges session-extracted keywords with ORCID research keywords into a single deduplicated list, **strongest first** (see [Keyword ageing](#keyword-ageing)). Expired keywords are left out.

`keywords` is a plain list, so consumers that ignore weights still get the priority order. `weightedKeywords` carries the weights.

```bash
curl http://localhost:8000/user/3f2e1d4c-.../profile
```

```json
{
  "userId": "3f2e1d4c-...",
  "keywords": ["knowledge graphs", "machine learning"],
  "weightedKeywords": [
    { "value": "knowledge graphs", "weight": 0.871, "source": "session" },
    { "value": "machine learning", "weight": 0.5, "source": "orcid" }
  ],
  "location": { "city": "Rome", "country": "Italy" },
  "affiliation": "CNR",
  "orcid": { "id": "0000-0002-1825-0097" }
}
```

Returns HTTP 404 if not found, same as `GET /user/{user_id}`.

---

### `POST /user` — Create a user

A `userId` (UUID) is generated automatically. Only `name`, `surname`, `age`, `email`, and `affiliation` are required.

**Minimal:**

```bash
curl -X POST http://localhost:8000/user \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Alice",
    "surname": "Rossi",
    "age": 34,
    "email": "alice.rossi@example.com",
    "affiliation": "University of Milan"
  }'
```

**Full** (with location, ORCID, session, and pre-set keywords):

```bash
curl -X POST http://localhost:8000/user \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Bob",
    "surname": "Verdi",
    "age": 41,
    "email": "bob.verdi@example.com",
    "affiliation": "CNR",
    "keywords": [{ "value": "knowledge graphs" }],
    "location": { "city": "Rome", "country": "Italy" },
    "orcid": {
      "id": "0000-0002-1825-0097",
      "keywords": [{ "value": "machine learning" }],
      "publications": [{
        "title": "Graph-Based User Profiling",
        "doi": "10.1000/xyz123",
        "journal": "Data Science Journal",
        "year": 2023,
        "authors": [{ "fullName": "Bob Verdi" }]
      }]
    },
    "sessions": [{
      "sessionId": "sess-001",
      "startTime": "2024-03-10T09:00:00",
      "endTime":   "2024-03-10T09:45:00",
      "extracted": false,
      "queries": [
        { "text": "knowledge graph embedding", "typedAt": "2024-03-10T09:05:00" }
      ]
    }]
  }'
```

---

### `DELETE /user/{user_id}` — Delete a user

Removes the user and all connected nodes (keywords, location, ORCID, publications, sessions, queries).

```bash
curl -X DELETE http://localhost:8000/user/3f2e1d4c-...
```

```json
{ "message": "User '3f2e1d4c-...' deleted." }
```

---

### `PATCH /user/{user_id}` — Edit a user

Partially updates a user. Only fields present in the body are changed. Nested objects (`location`, `orcid`, `sessions`, `keywords`) are replaced wholesale — to append a session, fetch the current profile first and re-submit the full array.

```bash
curl -X PATCH http://localhost:8000/user/3f2e1d4c-... \
  -H "Content-Type: application/json" \
  -d '{ "age": 42, "affiliation": "CNR - Institute of Cognitive Sciences" }'
```

---

### `GET /orcid/{orcid_id}` — Fetch a raw ORCID profile

Fetches the full public ORCID record for the given ORCID iD directly from the ORCID public API.

```bash
curl http://localhost:8000/orcid/0000-0001-6092-6831
```

Returns the raw ORCID JSON. Used internally by the Streamlit UI to auto-populate ORCID fields when creating or editing a user.

---

### `GET /user/{user_id}/generate-keywords` — Generate keywords from sessions

Calls the configured LLM with all queries from sessions not yet marked `extracted: true`. The LLM is asked for structured JSON (`{"keywords": [...]}`), which is validated, trimmed and de-duplicated before being returned.

```bash
curl http://localhost:8000/user/3f2e1d4c-.../generate-keywords
```

```json
{ "keywords": ["knowledge graphs", "graph embedding", "GNN"] }
```

Returns `{"keywords": []}` without calling the LLM if every session has already been extracted. Returns HTTP 502 if the LLM is unreachable, misconfigured, or replies with invalid output.

This endpoint only proposes keywords; nothing is saved. The Streamlit UI shows which ones are new, and **Accept & save** appends them with `POST /user/{user_id}/keywords` and marks the contributing sessions as `extracted: true`.

---

### `POST /user/{user_id}/keywords` — Append session keywords

Adds keywords without touching the existing ones. A keyword already saved (same value, ignoring case) is not duplicated: its `lastSeenAt` is refreshed, restoring its full weight.

```bash
curl -X POST http://localhost:8000/user/3f2e1d4c-.../keywords \
  -H "Content-Type: application/json" \
  -d '{ "keywords": ["GNN", "knowledge graphs"] }'
```

```json
{ "added": ["GNN"], "refreshed": ["knowledge graphs"] }
```

Use this rather than `PATCH /user/{id}` with `keywords`, which replaces the whole list. A `PATCH` still keeps the timestamps of keywords that stay in the list.

---

### `GET /user/{user_id}/keywords` — Keywords with their weights

All session and ORCID keywords with their current weight, strongest first, **including expired ones** (`"expired": true`). Used by the Streamlit UI to show how keywords are ageing.

```json
{ "keywords": [
  { "value": "GNN", "weight": 0.871, "source": "session", "lastSeenAt": "2026-09-25T10:00:00+00:00", "expired": false },
  { "value": "graphs", "weight": 0.06, "source": "session", "lastSeenAt": "2026-05-02T10:00:00+00:00", "expired": true }
] }
```

---

## Testing

### Interactive docs

The FastAPI automatic docs expose every endpoint with a built-in request builder:

```
http://localhost:8000/docs
```

### Example scripts

Ready-to-run scripts that exercise all endpoints end-to-end are in `examples/`. Each script starts with an empty database, creates two users, runs through all operations, and deletes both users so the database is clean at the end.

| File | Shell |
|---|---|
| `examples/api_examples.sh` | bash / WSL / Git Bash |
| `examples/api_examples.ps1` | PowerShell |

Run from the project root:

```bash
# bash
bash examples/api_examples.sh

# PowerShell
.\examples\api_examples.ps1
```
