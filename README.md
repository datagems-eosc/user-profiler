# User Profiler API

A FastAPI service for managing rich user profiles on a property graph, backed by [Grafeo](https://grafeo.dev). Each profile maps directly onto the PG-schema defined in `schema/user_model.pg` and captures identity, location, ORCID research output, and session activity.

## Project structure

```
user_profiler/
├── up_api/
│   ├── main.py                  # FastAPI app and endpoints
│   └── resources/
│       ├── data_models.py       # Pydantic models (node types + request bodies)
│       └── graph_helpers.py     # GQL utilities and graph CRUD operations
├── examples/
│   ├── api_examples.sh          # curl examples (bash)
│   └── api_examples.ps1         # curl examples (PowerShell)
├── schema/
│   └── user_model.pg            # PG-schema definition
└── requirements.txt
```

## Data model

The schema defines eight node types connected by typed edges:

```
User ──HAS_LOCATION──► Location
     ──HAS_ORCID──────► ORCID ──HAS_KEYWORD─────► Keyword
                              ──HAS_PUBLICATION──► Publication ──HAS_AUTHOR──► Author
     ──HAS_SESSION────► Session ──HAS_QUERY──► Query
```

## Setup

**Requirements:** Python 3.12+

```bash
pip install -r requirements.txt
```

Start the server from the project root:

```bash
uvicorn up_api.main:app --reload
```

The interactive API docs are available at `http://localhost:8000/docs`.

---

## Endpoints

### `GET /users` — List all user IDs

Returns a JSON object containing a list of every `userId` currently stored.

```bash
curl http://localhost:8000/users
```

```json
{
  "count": 2,
  "userIds": [
    "3f2e1d4c-...",
    "a1b2c3d4-..."
  ]
}
```

---

### `GET /user/{user_id}` — Retrieve a user

Returns the full profile for the given `userId`, or a message if the user does not exist.

```bash
curl http://localhost:8000/user/3f2e1d4c-...
```

```json
{
  "userId": "3f2e1d4c-...",
  "name": "Bob",
  "surname": "Verdi",
  "age": 41,
  "email": "bob.verdi@example.com",
  "affiliation": "CNR",
  "location": { "city": "Rome", "country": "Italy" },
  "orcid": null,
  "sessions": []
}
```

---

### `POST /user` — Create a user

Creates a new user. A `userId` (UUID) is generated automatically. Only `name`, `surname`, `age`, `email`, and `affiliation` are required; all other fields are optional.

**Minimal request:**

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

**Full request** (with location, ORCID, publications, and a session):

```bash
curl -X POST http://localhost:8000/user \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Bob",
    "surname": "Verdi",
    "age": 41,
    "email": "bob.verdi@example.com",
    "affiliation": "CNR",
    "location": { "city": "Rome", "country": "Italy" },
    "orcid": {
      "id": "0000-0002-1825-0097",
      "keywords": [
        { "value": "machine learning" },
        { "value": "knowledge graphs" }
      ],
      "publications": [
        {
          "title": "Graph-Based User Profiling",
          "doi": "10.1000/xyz123",
          "journal": "Data Science Journal",
          "year": 2023,
          "authors": [
            { "fullName": "Bob Verdi" },
            { "fullName": "Alice Rossi" }
          ]
        }
      ]
    },
    "sessions": [
      {
        "sessionId": "sess-001",
        "startTime": "2024-03-10T09:00:00",
        "endTime": "2024-03-10T09:45:00",
        "queries": [
          { "text": "knowledge graph embedding", "typedAt": "2024-03-10T09:05:00" }
        ]
      }
    ]
  }'
```

---

### `PATCH /user/{user_id}` — Edit a user

Partially updates an existing user. Only the fields included in the request body are changed. Returns the updated profile, or a message if the user does not exist.

`PATCH` replaces nested objects (e.g. `location`, `sessions`) wholesale — to append a session rather than replace the list, fetch the current profile first and re-submit the full sessions array.

```bash
curl -X PATCH http://localhost:8000/user/3f2e1d4c-... \
  -H "Content-Type: application/json" \
  -d '{
    "age": 42,
    "affiliation": "CNR — Institute of Cognitive Sciences"
  }'
```

---

## Examples

Ready-to-run example scripts covering all endpoints and edge cases are in the `examples/` folder:

| File | Shell |
|---|---|
| `examples/api_examples.sh` | bash / WSL / Git Bash |
| `examples/api_examples.ps1` | PowerShell (Windows) |
