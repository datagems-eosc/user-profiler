# Service Architecture

The User Profiler is an HTTP Api written in Python with [FastAPI](https://fastapi.tiangolo.com/) and served by [uvicorn](https://www.uvicorn.org/). User profiles are stored as a property graph in an embedded [Grafeo](https://grafeo.dev) database that lives inside the service process, as described in [Data Stores](datastore.md).

## Ecosystem

The service interacts with the following components:

* **DataGEMS AAI (Keycloak)**: issues the access tokens that callers present. The service downloads the realm's public keys (JWKS) to verify them. See [Security](security.md).
* **[Data Model Management (DMM)](https://datagems-eosc.github.io/data-model-management/)**: records the analytical patterns, and so the natural language queries, that users run on the platform. The service reads a user's recent queries from it to extract keywords.
* **LLM endpoint**: an OpenAI-compatible chat completions Api (in the DataGEMS deployment, the one served at `chat.scayle.es`). It extracts keywords from the queries.
* **[ORCID public Api](https://info.orcid.org/documentation/features/public-api/)**: provides public researcher records, used to fill in ORCID data for a profile.
* **[Query Recommender](https://datagems-eosc.github.io/query-recommender/)**: reads the portable interest profile to personalise its suggestions, and notifies this service of every query a user runs, which keeps the keywords up to date.
* **DataGEMS user interface**: shows and edits the user's own profile and keywords through the `/user/me` endpoints.

```
                         ┌──────────────────────┐
  Query Recommender ───▶ │    User Profiler     │ ──── JWKS ──────▶ DataGEMS AAI (Keycloak)
  UI, other clients      │        Api           │
  (Bearer token)         │                      │
                         │                      │ ── aplog search ─▶ DMM            (caller's token forwarded)
                         │  ┌────────────────┐  │ ── chat ─────────▶ LLM endpoint
                         │  │ Grafeo (graph) │  │ ── record ───────▶ ORCID public Api
                         │  └────────────────┘  │
                         └──────────────────────┘
```

## Data model

Each user is stored as a small subgraph, following the PG-schema in [`schema/user_model.pg`](https://github.com/datagems-eosc/user-profiler/blob/main/schema/user_model.pg):

```
User ──HAS_SESSION_KEYWORD──► Keyword          (session-extracted keywords)
     ──HAS_LOCATION─────────► Location
     ──HAS_ORCID────────────► ORCID ──HAS_KEYWORD─────► Keyword   (ORCID research keywords)
                                    ──HAS_PUBLICATION──► Publication ──HAS_AUTHOR──► Author
     ──HAS_SESSION──────────► Session ──HAS_QUERY──► Query
```

| Node | Properties |
|---|---|
| User | `userId`, `name`, `surname`, `dateOfBirth` (optional), `email`, `affiliation` |
| Keyword | `value`, `addedAt` and `lastSeenAt` (session keywords only) |
| Location | `city`, `country` |
| ORCID | `id` |
| Publication | `title`, `doi`, `journal`, `year` |
| Author | `fullName` |
| Session | `sessionId`, `startTime`, `endTime` (optional), `extracted` |
| Query | `text`, `typedAt` (optional) |

The `userId` is the subject (*sub* claim) of the user's DataGEMS access token, which is also the id under which the DMM logs the user's queries. Users created automatically, from a query notification or `POST /user/me`, get it from the token. The development endpoints can also create users with a generated or given UUID.

The queries read from the DMM are stored in one Session per user, with the fixed id `dmm-history`. It keeps the latest `MAX_STORED_QUERIES` queries (50 by default) and tells the service which queries have already been processed.

## Keyword ageing

Session keywords carry two timestamps: `addedAt`, when the keyword was first saved, and `lastSeenAt`, the last time it was extracted from the user's queries. Their **weight** decays with the time since `lastSeenAt`:

```
weight = 0.5 ^ (days since lastSeenAt / KEYWORD_HALF_LIFE_DAYS)
```

So a keyword weighs 1.0 when just seen, 0.5 after one half-life (30 days by default), 0.25 after two, and so on. Extracting a keyword again refreshes `lastSeenAt` and restores its full weight, so recurring interests stay strong.

ORCID keywords have no timestamps and always weigh `ORCID_KEYWORD_WEIGHT` (0.5 by default). When the same value is both a session and an ORCID keyword (ignoring case), the higher weight is kept.

Keywords whose weight drops below `KEYWORD_MIN_WEIGHT` (0.1 by default, about 100 days with the default half-life) **expire**. They stay in the graph and are still listed by `GET /user/{user_id}` and `GET /user/{user_id}/keywords`, but the portable profile stops returning them, so other services no longer use them. Extracting them again brings them back.

The parameters are described in [Configuration](configuration.md).

## Keyword refresh

Session keywords are kept up to date automatically, as the user runs queries on the platform:

```
UI ──query──▶ Query Recommender ──POST /user/{id}/queries──▶ User Profiler ──202──▶
                                                                  │ (background)
                                                                  ├─ GET aplog/search ──▶ DMM   (new queries only)
                                                                  ├─ chat ──────────────▶ LLM   (keywords)
                                                                  └─ save keywords + queries in the graph
```

1. **Notify.** When the Query Recommender receives a query, it calls `POST /user/{user_id}/queries`, forwarding the user's token. If the service has never seen the user, it creates them from the token's claims. It answers `202 Accepted` right away and continues in the background.
2. **Fetch.** The service reads the user's latest queries from the DMM (up to 50 natural language and cross-dataset discovery queries, with the forwarded token) and keeps only the ones newer than the last query in the `dmm-history` session. The notified query may not have reached the DMM yet: if it is not among the new queries, the service tries again, up to `DMM_QUERY_ATTEMPTS` times (3), `DMM_QUERY_RETRY_SECONDS` apart (2 s). It then goes on with whatever new queries it found.
3. **Extract.** If there are new queries, the LLM is asked for their keywords. The reply is requested as JSON of the form `{"keywords": [...]}`, constrained with a JSON schema where the LLM endpoint supports it, then validated, trimmed and de-duplicated.
4. **Save.** The keywords are appended to the profile: new ones are added, ones already present have their `lastSeenAt` refreshed, restoring their full weight. The new queries are added to `dmm-history`.

Refreshes of the same user run one at a time, so two notifications arriving together do not process the same queries twice. A refresh that fails (DMM or LLM unreachable, invalid LLM reply) changes nothing and is logged: the queries are picked up again by the next refresh. `GET /user/me/keywords` also starts a refresh when the user has no keywords yet, at most once every `KEYWORD_REFRESH_COOLDOWN_SECONDS` (60) per user. The service keeps in memory, per user, whether a refresh is running and whether the last one failed, and derives the status it returns from that (`pending`, `error`, ...). After a restart this is empty, so the first request starts a new refresh.

## Manual keyword extraction

Keywords can also be extracted on request, in two steps, so that a person or a client can review them before they are saved. The Streamlit interface uses this flow:

1. **Propose.** `GET /user/{user_id}/generate-keywords` reads the user's latest queries from the DMM (up to 50 natural language and cross-dataset discovery queries, using the caller's token) and asks the LLM for the relevant keywords. The reply is requested as JSON of the form `{"keywords": [...]}`, constrained with a JSON schema where the LLM endpoint supports it, then validated, trimmed and de-duplicated. Nothing is saved at this step.
2. **Save.** `POST /user/{user_id}/keywords` appends the accepted keywords to the profile. Keywords already present are not duplicated: their `lastSeenAt` is refreshed instead.

## Portable interest profile

`GET /user/{user_id}/profile` is the contract offered to other services. It returns only what is needed for personalisation: the active keywords, strongest first, as a plain list and with their weights and sources, plus location, affiliation and ORCID id. Personal data (`email`, `dateOfBirth`) and the raw session and query log are left out.

## Code layout

* `up_api/main.py`: the FastAPI application: lifespan of the database, Api root, and the routers below, all protected by token validation
* `up_api/routers/user.py`: user creation, retrieval, editing and deletion, for `/user/me` and `/user/{user_id}`, the interest profile and the ORCID lookup
* `up_api/routers/keywords.py`: the DMM client, query notifications, the keyword refresh, `/user/me/keywords` and `generate-keywords`
* `up_api/routers/dev.py`: the development endpoints (user creation with a generated or given id, `refresh-keyword_test`, `queries_test`)
* `up_api/resources/security.py`: token validation and the `authtest` endpoint
* `up_api/resources/graph_helpers.py`: GQL utilities and the graph read / write operations
* `up_api/resources/profile_helpers.py`: keyword weights, timestamps, the `dmm-history` session and the portable profile
* `up_api/resources/LLM_helpers.py`: model selection, prompt, LLM call and reply validation
* `up_api/resources/orcid_helpers.py`: ORCID public Api client
* `up_api/resources/data_models.py`: the node models and request bodies
* `schema/user_model.pg`: the PG-schema of the graph
* `examples/`: end to end example scripts, in bash and PowerShell
* `app.py` and `ui_local/`: a Streamlit user interface for testing, described in [Onboarding](onboarding.md). Each tab is a module in `ui_local/tabs/`
