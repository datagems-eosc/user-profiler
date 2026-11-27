# Logging

The service writes its logs to standard output, where they are collected by the container runtime. In the DataGEMS cluster they can be read with the usual Kubernetes tooling, e.g. `kubectl logs -n univr deployment/user-profiler`.

## Access logs

Each request served is logged by uvicorn in its standard access log format, with the client address, method, path and status code:

```
INFO:     10.0.0.12:53124 - "GET /user/3f2e1d4c-.../profile HTTP/1.1" 200 OK
```

## Troubleshooting logs

The service logs the conditions that are hidden from the caller behind a generic error, or handled without failing the request:

| Message | Meaning |
|---|---|
| `JWT validation failed: ...` | A token was rejected (401). The message gives the reason, e.g. an expired signature |
| `Could not reach models endpoint: ...` | The list of available LLM models could not be fetched, so the preferred model name was used as is |
| `Error while calling API: ...` | The LLM call failed (502 to the caller) |
| `LLM reply contains no JSON object: ...` | The LLM replied without any JSON (502 to the caller). The reply is included |
| `LLM reply does not match the expected schema: ...` | The LLM replied with JSON of the wrong shape (502 to the caller) |
| `WARNING: TLS certificate verification for the LLM API is disabled ...` | Printed at startup when `LLM_SSL_VERIFY=false` |

For `generate-keywords` and `queries_test`, DMM errors are not logged separately, as their details are returned to the caller in the 502 response, see [Status & Error Codes](error-codes.md).

## Keyword refresh logs

The keyword refresh runs in the background after a query notification, so its outcome is only visible in the logs. These lines are written by the `up_api.routers.keywords` and `up_api.routers.user` loggers, in the format `<time> <level> <logger>: <message>`:

| Level | Message | Meaning |
|---|---|---|
| INFO | `Query notified for <user_id>: '<query>'` | A query notification was received and a refresh started |
| INFO | `User <user_id> not in the graph: created from the token` | The user was unknown and was created from the token's claims |
| INFO | `Refresh of <user_id>: dmm=... llm=... added=[...] refreshed=[...] detail=...` | Outcome of a refresh: `dmm` is `ok` or `error`, `llm` is `ok`, `error` or `skipped` (no new queries), followed by the new and refreshed keywords |
| INFO | `Refresh of <user_id>: notified query already processed: '<query>'` | The notified query had already been processed by an earlier refresh, e.g. when the same query is notified twice |
| WARNING | `Refresh of <user_id>: notified query not found in the DMM after <n> attempts: '<query>'` | The DMM did not have the notified query yet after all the attempts. Any other new queries are still processed, and the missing one is picked up by a later refresh |
| WARNING | `Keyword refresh of <user_id>: <detail>` | The DMM or the LLM failed. Nothing was saved |
| ERROR | `Keyword refresh of <user_id>: unexpected LLM error` | The LLM call raised an unexpected error. The stack trace follows |
| ERROR | `Refresh of <user_id> failed` | The refresh failed for an unexpected reason. The stack trace follows |

To follow the refreshes of one user in the DataGEMS cluster:

```bash
kubectl logs -n univr deployment/user-profiler | grep <user_id>
```

The service does not currently produce structured (JSON) logs, propagate a correlation identifier, or emit accounting entries.
