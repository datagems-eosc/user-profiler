# Maintenance

The service is part of the DataGEMS platform offered through an existing deployment, following the DataGEMS release and deployment procedures over a managed infrastructure along with the maintenance activities that are scheduled within the platform. The purpose of this section is not to detail the maintenance activities put in place by the DataGEMS team.

## Healthchecks

The Api root, `GET /api/v1`, does not require authentication and answers `200 OK` as soon as the service is up. It can be used as a liveness check:

```bash
curl https://datagems-dev.scayle.es/up/api/v1
```

```json
{ "message": "User Profiler API V1 is running" }
```

This check does not cover the database or the underpinning services. To also verify authentication and the database end to end, call `GET /users` with a valid token. To verify the DMM connection, use `GET /user/{user_id}/queries_test`.

In Kubernetes, the readiness of the container is checked with a TCP probe on port 5000.

## Versions & Updates

The service follows a semantic versioning scheme and structures versions as MAJOR.MINOR.PATCH:

* MAJOR (X.0.0): Breaking changes that are incompatible with previous versions.
* MINOR (X.Y.0): New features added in a backward-compatible way.
* PATCH (X.Y.Z): Bug fixes and security patches that do not affect compatibility.

Each version is released by pushing a `vX.Y.Z` tag, which builds and publishes the matching Docker image, as described in [Automations](automations.md).

Keywords saved by older versions, before keyword timestamps existed, are stamped the next time the user's profile is saved.

## Backups

All state is kept in the Grafeo database folder (`GRAFEO_DB_PATH`), as described in [Data Stores](datastore.md). Backing up the service means copying that folder. To get a consistent copy, take it while the service is stopped, or from a snapshot of the persistent volume.

To keep backups of the state, the copy must be scheduled to run in a consistent manner.

## Troubleshooting

Troubleshooting is primarily done through the logs, described in the respective [logging](logging.md) section. Common symptoms and their usual causes are:

* **401 on every call**: the token is expired, or was issued by a different realm than `OIDC_ISSUER_URL`
* **403 on every call**: the token audience contains neither `user-profiler` nor `query-recommender`
* **All users disappear after a redeploy**: `GRAFEO_DB_PATH` is not on a persistent volume
* **Keyword generation answers 502 with `The DMM returned 401` or `403`**: the token is not accepted by the DMM. It needs the DMM audience as well
* **Keyword generation answers 502 with the LLM message**: the LLM endpoint is unreachable, `LLM_TOKEN` is wrong, or TLS verification is failing (look for `CERTIFICATE_VERIFY_FAILED` in the logs)
* **Keyword generation always returns an empty list**: the DMM has no queries for that user id. Check that the profile was created with the same id the DMM logs the user under
