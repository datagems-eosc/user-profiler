#!/usr/bin/env bash
# User Profiler API — curl examples
# Start the server first: uvicorn up_api.main:app --reload

BASE="http://localhost:8000"
extract_id() { python -c "import sys,json; print(json.load(sys.stdin)['userId'])"; }

# ---------------------------------------------------------------------------
# 0. List all users (empty at start)
# ---------------------------------------------------------------------------
echo -e "\n--- 0. List all users ---"
curl -s "$BASE/users" | python -m json.tool

# ---------------------------------------------------------------------------
# 1. Create a minimal user  (required fields only)
# ---------------------------------------------------------------------------
echo -e "\n--- 1. Create minimal user ---"
RESP1=$(curl -s -X POST "$BASE/user" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Alice",
    "surname": "Rossi",
    "age": 34,
    "email": "alice.rossi@example.com",
    "affiliation": "University of Milan"
  }')
echo "$RESP1" | python -m json.tool
USER1_ID=$(echo "$RESP1" | extract_id)

# ---------------------------------------------------------------------------
# 2. Create a full user  (location + ORCID + publications + session)
# ---------------------------------------------------------------------------
echo -e "\n--- 2. Create full user ---"
RESP2=$(curl -s -X POST "$BASE/user" \
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
  }')
echo "$RESP2" | python -m json.tool
USER2_ID=$(echo "$RESP2" | extract_id)

# ---------------------------------------------------------------------------
# 3. List users (should show Alice and Bob)
# ---------------------------------------------------------------------------
echo -e "\n--- 3. List users ---"
curl -s "$BASE/users" | python -m json.tool

# ---------------------------------------------------------------------------
# 4. Get a user by ID
# ---------------------------------------------------------------------------
echo -e "\n--- 4. Get user by ID ---"
curl -s "$BASE/user/$USER2_ID" | python -m json.tool

# ---------------------------------------------------------------------------
# 5. Get a user that does not exist
# ---------------------------------------------------------------------------
echo -e "\n--- 5. Get non-existent user ---"
curl -s "$BASE/user/nonexistent-id-000" | python -m json.tool

# ---------------------------------------------------------------------------
# 6. Edit a user — update scalar fields
# ---------------------------------------------------------------------------
echo -e "\n--- 6. Edit scalar fields ---"
curl -s -X PATCH "$BASE/user/$USER2_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "age": 42,
    "affiliation": "CNR — Institute of Cognitive Sciences"
  }' | python -m json.tool

# ---------------------------------------------------------------------------
# 7. Edit a user — replace location
# ---------------------------------------------------------------------------
echo -e "\n--- 7. Replace location ---"
curl -s -X PATCH "$BASE/user/$USER2_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "location": {
      "city": "Turin",
      "country": "Italy"
    }
  }' | python -m json.tool

# ---------------------------------------------------------------------------
# 8. Edit a user — replace sessions list
# ---------------------------------------------------------------------------
echo -e "\n--- 8. Replace sessions ---"
curl -s -X PATCH "$BASE/user/$USER2_ID" \
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
# 9. Edit a non-existent user
# ---------------------------------------------------------------------------
echo -e "\n--- 9. Edit non-existent user ---"
curl -s -X PATCH "$BASE/user/nonexistent-id-000" \
  -H "Content-Type: application/json" \
  -d '{ "age": 99 }' | python -m json.tool

# ---------------------------------------------------------------------------
# 10. Delete a non-existent user
# ---------------------------------------------------------------------------
echo -e "\n--- 10. Delete non-existent user ---"
curl -s -X DELETE "$BASE/user/nonexistent-id-000" | python -m json.tool

# ---------------------------------------------------------------------------
# 11. Delete both users
# ---------------------------------------------------------------------------
echo -e "\n--- 11. Delete Alice ---"
curl -s -X DELETE "$BASE/user/$USER1_ID" | python -m json.tool

echo -e "\n--- 11. Delete Bob ---"
curl -s -X DELETE "$BASE/user/$USER2_ID" | python -m json.tool

# ---------------------------------------------------------------------------
# 12. List users (should be empty again)
# ---------------------------------------------------------------------------
echo -e "\n--- 12. List users (empty) ---"
curl -s "$BASE/users" | python -m json.tool
