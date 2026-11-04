# Api Overview

The service exposes an HTTP Api with JSON request and response bodies. In the DataGEMS development deployment it is reachable at `https://datagems-dev.scayle.es/up`.

The full, machine readable description is available in the [OpenAPI Reference](openapi.md). A running instance also serves it at:

* `/api/v1/openapi.json`: the OpenAPI document
* `/api/v1/swagger`: Swagger UI
* `/api/v1/redoc`: ReDoc

Note that the user endpoints are served at the root of the service (e.g. `/users`, `/user/{user_id}`), while the Api root and the auth test endpoint are under `/api/v1`.

## Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1` | Api root: confirms the Api is running. No authentication |
| POST | `/api/v1/authtest` | Checks that a bearer token is accepted by the service |
| GET | `/users` | Lists all users |
| POST | `/user` | Creates a user, with a generated id |
| POST | `/user/{user_id}` | Creates a user with a given id (e.g. the DMM one) |
| GET | `/user/{user_id}` | Returns the full profile of a user |
| PATCH | `/user/{user_id}` | Edits a user |
| DELETE | `/user/{user_id}` | Deletes a user and everything connected to them |
| GET | `/user/{user_id}/profile` | Returns the portable interest profile of a user |
| GET | `/user/{user_id}/keywords` | Lists all keywords of a user with their current weight |
| POST | `/user/{user_id}/keywords` | Appends session keywords to a user |
| GET | `/user/{user_id}/generate-keywords` | Proposes keywords from the user's recent queries |
| GET | `/user/{user_id}/queries_test` | Development: the user's queries as read from the DMM |
| GET | `/orcid/{orcid_id}` | Returns a raw ORCID public record |

All endpoints under `/user/{user_id}` answer `404 Not Found` with `{"detail": "No such user: '...'"}` if the user does not exist.

## Users

### List users

`GET /users`

```json
{
  "count": 2,
  "users": [
    { "userId": "3f2e1d4c-...", "name": "Alice", "surname": "Rossi" },
    { "userId": "a1b2c3d4-...", "name": "Bob", "surname": "Verdi" }
  ]
}
```

### Create a user

`POST /user` creates a user with a generated UUID and answers `201 Created` with the full profile. `POST /user/{user_id}` does the same with the given id, which must be a lowercase, hyphenated UUID (otherwise `422`), and answers `409 Conflict` if a user with that id already exists. Use the latter to create the profile under the same id the DMM logs the user's queries with.

Only `name`, `surname`, `email` and `affiliation` are required:

```json
{
  "name": "Alice",
  "surname": "Rossi",
  "email": "alice.rossi@example.com",
  "affiliation": "University of Milan"
}
```

A full body can also include the date of birth, initial session keywords, location, ORCID data and sessions:

```json
{
  "name": "Bob",
  "surname": "Verdi",
  "dateOfBirth": "1984-05-12T00:00:00",
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
    "endTime": "2024-03-10T09:45:00",
    "extracted": false,
    "queries": [
      { "text": "knowledge graph embedding", "typedAt": "2024-03-10T09:05:00" }
    ]
  }]
}
```

Unknown fields are ignored. Keywords without timestamps are stamped as seen at creation time.

### Retrieve a user

`GET /user/{user_id}` returns the full profile, as stored:

```json
{
  "userId": "3f2e1d4c-...",
  "name": "Alice",
  "surname": "Rossi",
  "dateOfBirth": null,
  "email": "alice.rossi@example.com",
  "affiliation": "University of Milan",
  "keywords": [],
  "location": null,
  "orcid": null,
  "sessions": []
}
```

### Edit a user

`PATCH /user/{user_id}` changes only the fields present in the body and returns the updated profile. Nested objects and lists (`location`, `orcid`, `sessions`, `keywords`) are replaced as a whole: to add a session, fetch the profile, add it to the list, and send the full list back. Keywords that stay in the list keep their timestamps, new ones are stamped as seen now.

```json
{ "affiliation": "CNR - Institute of Cognitive Sciences" }
```

To add keywords, prefer `POST /user/{user_id}/keywords`, which does not replace the existing ones.

### Delete a user

`DELETE /user/{user_id}` removes the user and all connected nodes (keywords, location, ORCID, publications, sessions and queries):

```json
{ "message": "User '3f2e1d4c-...' deleted." }
```

## Interest profile

`GET /user/{user_id}/profile`

The portable profile meant for other services. It merges session and ORCID keywords into one de-duplicated list, strongest first, and leaves out expired keywords, personal data and the session log. See [Keyword ageing](architecture.md#keyword-ageing).

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

`keywords` is a plain list, so consumers that ignore weights still get the priority order. `weightedKeywords` carries the weights and the source (`session` or `orcid`) of each one.

## Keywords

### List keywords with weights

`GET /user/{user_id}/keywords` returns all session and ORCID keywords with their current weight, strongest first, **including expired ones**:

```json
{
  "keywords": [
    { "value": "GNN", "weight": 0.871, "source": "session", "lastSeenAt": "2026-09-25T10:00:00+00:00", "expired": false },
    { "value": "machine learning", "weight": 0.5, "source": "orcid", "lastSeenAt": null, "expired": false },
    { "value": "graphs", "weight": 0.06, "source": "session", "lastSeenAt": "2026-05-02T10:00:00+00:00", "expired": true }
  ]
}
```

### Generate keywords

`GET /user/{user_id}/generate-keywords` reads the user's latest queries from the DMM (up to 50 natural language and cross-dataset discovery queries) and asks the LLM for the keywords that describe them:

```json
{ "keywords": ["knowledge graphs", "graph embedding", "GNN"] }
```

Nothing is saved: the result is a proposal, to be saved with `POST /user/{user_id}/keywords`. The endpoint returns `{"keywords": []}` without calling the LLM if the DMM has no queries for the user. It answers `502 Bad Gateway` if the DMM or the LLM cannot be reached, if the DMM rejects the forwarded token, or if the LLM replies with invalid output.

The call can take a while, as it waits for both the DMM and the LLM. Clients should use a generous timeout.

### Append keywords

`POST /user/{user_id}/keywords` adds session keywords without touching the existing ones. A value already saved (ignoring case) is not duplicated: its `lastSeenAt` is refreshed, restoring its full weight.

```json
{ "keywords": ["GNN", "knowledge graphs"] }
```

```json
{ "added": ["GNN"], "refreshed": ["knowledge graphs"] }
```

## DMM queries (development)

`GET /user/{user_id}/queries_test` returns the queries the DMM has logged for the given user id, keyed by timestamp. It is the same lookup `generate-keywords` uses, exposed to check the DMM connection. The token must be accepted by the DMM too.

```json
{
  "user_id": "ee01595a-ceec-4f54-8ece-f5e967f6036e",
  "count": 2,
  "queries": {
    "2026-10-20T09:12:44": "average rainfall in Lombardy",
    "2026-10-20T09:15:02": "rainfall datasets for northern Italy"
  }
}
```

## ORCID

`GET /orcid/{orcid_id}` fetches the full public ORCID record for the given ORCID iD from the [ORCID public Api](https://info.orcid.org/documentation/features/public-api/) and returns it unchanged. It is used by the Streamlit interface to fill in ORCID data when creating or editing a user. Nothing is saved.

## Auth test

`POST /api/v1/authtest`

Validates the caller's token (signature, issuer, expiry and audience) and echoes back the request and the identity found in the token. The request body has the same shape as the auth test endpoints of the other DataGEMS Apis, and no other fields are allowed:

```json
{ "query": "test", "k": 1 }
```

```json
{
  "authorized": true,
  "message": "Token is valid",
  "request": { "query": "test", "k": 1 },
  "subject": "the subject id",
  "username": "the preferred username"
}
```

## Api root

`GET /api/v1` does not require authentication:

```json
{ "message": "User Profiler API V1 is running" }
```

`GET /` redirects to it.
