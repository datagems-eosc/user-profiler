#!/usr/bin/env bash
# User Profiler API — curl examples
# Start the server first: uvicorn main:app --reload

BASE="http://localhost:8000"

# ---------------------------------------------------------------------------
# 0. List all user IDs
# ---------------------------------------------------------------------------
curl -s "$BASE/users" | python -m json.tool

# ---------------------------------------------------------------------------
# 1. Create a minimal user  (required fields only)
# ---------------------------------------------------------------------------
curl -s -X POST "$BASE/user" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Alice",
    "surname": "Rossi",
    "age": 34,
    "email": "alice.rossi@example.com",
    "affiliation": "University of Milan"
  }' | python -m json.tool

# ---------------------------------------------------------------------------
# 2. Create a full user  (location + ORCID + publications + session)
# ---------------------------------------------------------------------------
curl -s -X POST "$BASE/user" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Bob",
    "surname": "Verdi",
    "age": 41,
    "email": "bob.verdi@example.com",
    "affiliation": "CNR",
    "location": {
      "city": "Rome",
      "country": "Italy"
    },
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
          { "text": "knowledge graph embedding", "typedAt": "2024-03-10T09:05:00" },
          { "text": "GNN survey 2023",            "typedAt": "2024-03-10T09:20:00" }
        ]
      }
    ]
  }' | python -m json.tool

# ---------------------------------------------------------------------------
# 3. Get a user by ID  (replace USER_ID with the id returned by create)
# ---------------------------------------------------------------------------
USER_ID="<paste-userId-here>"

curl -s "$BASE/user/$USER_ID" | python -m json.tool

# ---------------------------------------------------------------------------
# 4. Get a user that does not exist
# ---------------------------------------------------------------------------
curl -s "$BASE/user/nonexistent-id-000" | python -m json.tool

# ---------------------------------------------------------------------------
# 5. Edit a user — update scalar fields
# ---------------------------------------------------------------------------
curl -s -X PATCH "$BASE/user/$USER_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "age": 42,
    "affiliation": "CNR — Institute of Cognitive Sciences"
  }' | python -m json.tool

# ---------------------------------------------------------------------------
# 6. Edit a user — replace location
# ---------------------------------------------------------------------------
curl -s -X PATCH "$BASE/user/$USER_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "location": {
      "city": "Turin",
      "country": "Italy"
    }
  }' | python -m json.tool

# ---------------------------------------------------------------------------
# 7. Edit a user — append a new session
#    (PATCH replaces the sessions list; fetch first if you want to append)
# ---------------------------------------------------------------------------
curl -s -X PATCH "$BASE/user/$USER_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "sessions": [
      {
        "sessionId": "sess-002",
        "startTime": "2024-04-01T14:00:00",
        "queries": [
          { "text": "transformer architectures", "typedAt": "2024-04-01T14:03:00" }
        ]
      }
    ]
  }' | python -m json.tool

# ---------------------------------------------------------------------------
# 8. Edit a non-existent user
# ---------------------------------------------------------------------------
curl -s -X PATCH "$BASE/user/nonexistent-id-000" \
  -H "Content-Type: application/json" \
  -d '{ "age": 99 }' | python -m json.tool
