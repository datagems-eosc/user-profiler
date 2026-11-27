# Frequently Asked Questions (FAQ)

## What is the difference between `/user/{user_id}` and `/user/{user_id}/profile`?

`/user/{user_id}` returns everything the service stores about the user, including personal data and the session log. `/user/{user_id}/profile` is the portable profile meant for other services: active keywords ranked by weight, location, affiliation and ORCID id only. Services that personalise their behaviour should use the latter.

## Why did a keyword disappear from the profile?

Its weight dropped below `KEYWORD_MIN_WEIGHT` because it was not seen for a long time (about 100 days with the default settings). It is still stored and listed by `/user/{user_id}/keywords` with `"expired": true`, and comes back if it is extracted again. See [Keyword ageing](architecture.md#keyword-ageing).

## How do users get keywords?

Automatically. Every time a user runs a query, the Query Recommender notifies this service (`POST /user/{user_id}/queries`), which reads the user's new queries from the DMM, extracts their keywords with the LLM and saves them. Users do not need to create their profile first: it is created from their token at their first query. See [Keyword refresh](architecture.md#keyword-refresh).

## I ran a query, but my keywords did not change

The refresh runs in the background, after the notification has been answered, and takes a few seconds (longer the first time, when all the user's latest queries are processed). If the keywords still do not change, look for the user's id in the logs (see [Logging](logging.md)): the refresh logs its outcome, including DMM and LLM errors. The development endpoint `refresh-keyword_test` runs a refresh and returns its outcome directly.

## Why doesn't keyword generation save anything?

On purpose: `generate-keywords` only proposes keywords, so they can be reviewed first. Save the ones you want with `POST /user/{user_id}/keywords`. The automatic refresh, instead, saves the keywords it extracts.

## Keyword generation always returns an empty list

The DMM has no queries logged under that user id. Profiles must have the same id the DMM uses for the user, i.e. the subject of the user's token. Profiles created automatically always do. The `queries_test` endpoint, or the **DMM queries** tab of the Streamlit interface, shows what the DMM has for a given id.

## Keyword generation fails with "The DMM returned 401"

Your token is not accepted by the DMM. As the service forwards your token to the DMM, it needs the DMM audience as well as this service's. The same applies to the automatic refresh, which logs the error instead.

## What is the difference between `/user/me` and `/user/{user_id}`?

`/user/me` works on the user the token belongs to, and is meant for the DataGEMS user interface: users see and edit their own profile without knowing their id. The `/user/me` endpoints leave out keywords and sessions, which `GET /user/me/keywords` and the interface itself show, and `PATCH /user/me` cannot change them. `/user/{user_id}` works on any user and returns everything.

## Should I use `PATCH` to add keywords?

No. `PATCH /user/{user_id}` replaces the whole keyword list. Use `POST /user/{user_id}/keywords`, which appends new keywords and refreshes the existing ones.

## Can I run more than one replica?

No. The embedded database can only be used by one process at a time, so the service must run as a single replica. See [Data Stores](datastore.md).

## Known Issues

* There are no per-user permissions: any accepted token can read and change any profile. See [Security](security.md).
* Writes rewrite the whole user subgraph, so concurrent writes to the same user can overwrite each other. Keyword refreshes of the same user run one at a time, but an edit made while a refresh is waiting for the LLM can still be overwritten by it.
* `query-recommender` is accepted as an audience as a temporary workaround, until the DataGEMS Keycloak configuration adds `user-profiler` to the tokens the Query Recommender forwards.
* The user endpoints are served at the root of the service rather than under `/api/v1`, unlike the Api root and the auth test endpoint.
* `GET /` redirects to `/api/v1` without taking the proxy prefix into account. Behind the DataGEMS ingress, use `/up/api/v1` directly.
