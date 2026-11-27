# Api Overview

The service exposes an HTTP Api with JSON request and response bodies. In the DataGEMS development deployment it is reachable at `https://datagems-dev.scayle.es/up`. In production it is internal to the cluster, and reached by the other DataGEMS services at `http://user-profiler-service:5000`.

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
| **Token's own user** | | *For the DataGEMS user interface: the user is the token's subject* |
| POST | `/user/me` | Creates the token's own user, or completes it if it already exists |
| GET | `/user/me` | Returns the token's own user, without keywords and sessions |
| PATCH | `/user/me` | Edits the token's own user |
| DELETE | `/user/me` | Deletes the token's own user |
| GET | `/user/me/keywords` | Lists the keywords of the token's own user, with their status |
| **Users by id** | | |
| GET | `/users` | Lists all users |
| GET | `/user/{user_id}` | Returns the full profile of a user |
| PATCH | `/user/{user_id}` | Edits a user |
| DELETE | `/user/{user_id}` | Deletes a user and everything connected to them |
| GET | `/user/{user_id}/profile` | Returns the portable interest profile of a user |
| GET | `/user/{user_id}/keywords` | Lists all keywords of a user with their current weight |
| POST | `/user/{user_id}/keywords` | Appends session keywords to a user |
| POST | `/user/{user_id}/queries` | Notifies a new query of the user, which triggers a keyword refresh |
| GET | `/user/{user_id}/generate-keywords` | Proposes keywords from the user's recent queries, without saving them |
| GET | `/orcid/{orcid_id}` | Returns a raw ORCID public record |
| **Development** | | *Kept for testing, not used by the DataGEMS UI or the Query Recommender* |
| POST | `/user` | Creates a user, with a generated id |
| POST | `/user/{user_id}` | Creates a user with a given id (e.g. the DMM one) |
| POST | `/user/{user_id}/refresh-keyword_test` | Runs a keyword refresh and waits for its outcome |
| GET | `/user/{user_id}/queries_test` | The user's queries as read from the DMM |

All endpoints under `/user/{user_id}` answer `404 Not Found` with `{"detail": "No such user: '...'"}` if the user does not exist. The `/user/me` endpoints do the same when the token's subject has no profile yet, except `POST /user/me`, which creates it, and `GET /user/me/keywords`, which answers with a status.

## Token's own user

These endpoints are meant for the DataGEMS user interface, e.g. a profile or settings page. They take no user id: the user is the subject (*sub* claim) of the access token, which is also the id the DMM logs the user's queries under. Users do not need to create their profile: the service creates it the first time it is notified of one of their queries (see [Query notifications](#query-notifications)). `POST /user/me` is there for users who open their profile before running any query.

### Create or complete

`POST /user/me` takes the user's name, surname and email from the token (`given_name` or `preferred_username`, `family_name`, `email`). The affiliation is set to `unknown`. The body is optional: its fields complete or override the ones from the token, and it accepts the same fields as `PATCH /user/{user_id}`:

```json
{ "affiliation": "University of Verona" }
```

If the user does not exist yet, the service answers `201 Created` with the full profile. If it already exists (for example, created by a query notification), the body is applied as an edit and the service answers `200 OK` with the updated profile.

### Retrieve

`GET /user/me` returns the profile without `keywords` and `sessions`: the keywords have their own endpoint, and the user interface already displays the queries.

```json
{
  "userId": "16a5380f-...",
  "name": "Alice",
  "surname": "Rossi",
  "dateOfBirth": null,
  "email": "alice.rossi@example.com",
  "affiliation": "University of Verona",
  "location": null,
  "orcid": null
}
```

### Edit

`PATCH /user/me` changes only the fields present in the body and returns the full updated profile. The editable fields are `name`, `surname`, `dateOfBirth`, `email`, `affiliation`, `location` and `orcid`. Keywords and sessions cannot be changed through this endpoint: they are ignored if sent. As with `PATCH /user/{user_id}`, `location` and `orcid` are replaced as a whole.

```json
{ "orcid": { "id": "0000-0002-1825-0097", "keywords": [], "publications": [] } }
```

### Delete

`DELETE /user/me` removes the user and everything connected to them:

```json
{ "message": "User '16a5380f-...' deleted." }
```

### Keywords

`GET /user/me/keywords` returns the same keyword list as `GET /user/{user_id}/keywords` (see [List keywords with weights](#list-keywords-with-weights)), with a `status` telling the interface what to show:

| `status` | Meaning |
|---|---|
| `ok` | The keywords are in `keywords` |
| `pending` | The user has no keywords yet and their queries were never processed. A refresh from the DMM has been started: reload in a few seconds |
| `no_keywords` | The user's queries were processed, but no keywords came out. A new refresh has been started |
| `no_queries` | The service has never seen this user |

```json
{
  "status": "ok",
  "keywords": [
    { "value": "weather", "weight": 1.0, "source": "session", "lastSeenAt": "2026-11-27T13:02:59+00:00", "expired": false }
  ]
}
```

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

### Create a user (development)

In normal operation, users are created automatically from their token, either by a [query notification](#query-notifications) or by `POST /user/me`. The two endpoints below are kept for testing.

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

The queries read from the DMM are kept in a session with id `dmm-history` (see [Keyword refresh](architecture.md#keyword-refresh)).

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

## Query notifications

`POST /user/{user_id}/queries` tells the service that the user has just run a query on the platform. The Query Recommender calls it, forwarding the user's token, every time it receives a query:

```json
{ "query": "average temperature in Athens in July" }
```

The service answers `202 Accepted` immediately, then refreshes the user's keywords in the background:

```json
{ "status": "accepted", "created": false }
```

If the service has never seen the user, it first creates them from the token's claims, as `POST /user/me` does, and `created` is `true`. This only happens when `user_id` is the token's own subject: notifying a query for an unknown user other than oneself answers `404`.

The refresh reads the user's new queries from the DMM, asks the LLM for their keywords and saves them. As the query may not have reached the DMM yet, the service retries a few times if it is not among the queries returned. The outcome is not returned to the caller, but logged. See [Keyword refresh](architecture.md#keyword-refresh) and [Logging](logging.md).

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

Nothing is saved: the result is a proposal, to be saved with `POST /user/{user_id}/keywords`. Unlike the automatic refresh, it always looks at all of the latest queries, not only the new ones. The endpoint returns `{"keywords": []}` without calling the LLM if the DMM has no queries for the user. It answers `502 Bad Gateway` if the DMM or the LLM cannot be reached, if the DMM rejects the forwarded token, or if the LLM replies with invalid output.

The call can take a while, as it waits for both the DMM and the LLM. Clients should use a generous timeout.

### Append keywords

`POST /user/{user_id}/keywords` adds session keywords without touching the existing ones. A value already saved (ignoring case) is not duplicated: its `lastSeenAt` is refreshed, restoring its full weight.

```json
{ "keywords": ["GNN", "knowledge graphs"] }
```

```json
{ "added": ["GNN"], "refreshed": ["knowledge graphs"] }
```

## Development endpoints

### Refresh keywords

`POST /user/{user_id}/refresh-keyword_test` runs the same refresh as a query notification, but waits for it and returns its outcome. The user must exist.

```json
{
  "dmm": "ok",
  "llm": "ok",
  "detail": null,
  "added": ["weather", "Athens"],
  "refreshed": ["temperature"]
}
```

`dmm` is `ok` or `error`. `llm` is `ok`, `error`, or `skipped` when there were no new queries to process. `detail` explains an error. Errors of the DMM or the LLM are reported in the body, with status `200`.

### DMM queries

`GET /user/{user_id}/queries_test` returns the queries the DMM has logged for the given user id (up to 50, natural language and cross-dataset discovery queries). It is the same lookup the keyword refresh and `generate-keywords` use, exposed to check the DMM connection. The token must be accepted by the DMM too.

```json
{
  "user_id": "ee01595a-ceec-4f54-8ece-f5e967f6036e",
  "count": 2,
  "queries": [
    { "text": "rainfall datasets for northern Italy", "typedAt": "2026-10-20T09:15:02Z" },
    { "text": "average rainfall in Lombardy", "typedAt": "2026-10-20T09:12:44Z" }
  ]
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
