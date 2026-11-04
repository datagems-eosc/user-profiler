# Frequently Asked Questions (FAQ)

## What is the difference between `/user/{user_id}` and `/user/{user_id}/profile`?

`/user/{user_id}` returns everything the service stores about the user, including personal data and the session log. `/user/{user_id}/profile` is the portable profile meant for other services: active keywords ranked by weight, location, affiliation and ORCID id only. Services that personalise their behaviour should use the latter.

## Why did a keyword disappear from the profile?

Its weight dropped below `KEYWORD_MIN_WEIGHT` because it was not seen for a long time (about 100 days with the default settings). It is still stored and listed by `/user/{user_id}/keywords` with `"expired": true`, and comes back if it is extracted again. See [Keyword ageing](architecture.md#keyword-ageing).

## Why doesn't keyword generation save anything?

On purpose: `generate-keywords` only proposes keywords, so they can be reviewed first. Save the ones you want with `POST /user/{user_id}/keywords`.

## Keyword generation always returns an empty list

The DMM has no queries logged under that user id. Profiles must be created with the same id the DMM uses for the user (`POST /user/{user_id}`). The `queries_test` endpoint, or the **DMM queries** tab of the Streamlit interface, shows what the DMM has for a given id.

## Keyword generation fails with "The DMM returned 401"

Your token is not accepted by the DMM. As the service forwards your token to the DMM, it needs the DMM audience as well as this service's.

## Should I use `PATCH` to add keywords?

No. `PATCH /user/{user_id}` replaces the whole keyword list. Use `POST /user/{user_id}/keywords`, which appends new keywords and refreshes the existing ones.

## Can I run more than one replica?

No. The embedded database can only be used by one process at a time, so the service must run as a single replica. See [Data Stores](datastore.md).

## Known Issues

* There are no per-user permissions: any accepted token can read and change any profile. See [Security](security.md).
* Writes rewrite the whole user subgraph, so concurrent writes to the same user can overwrite each other.
* `query-recommender` is accepted as an audience as a temporary workaround, until the DataGEMS Keycloak configuration adds `user-profiler` to the tokens the Query Recommender forwards.
* The user endpoints are served at the root of the service rather than under `/api/v1`, unlike the Api root and the auth test endpoint.
* `GET /` redirects to `/api/v1` without taking the proxy prefix into account. Behind the DataGEMS ingress, use `/up/api/v1` directly.
