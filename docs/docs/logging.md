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

DMM errors are not logged separately, as their details are returned to the caller in the 502 response, see [Status & Error Codes](error-codes.md).

The service does not currently produce structured (JSON) logs, propagate a correlation identifier, or emit accounting entries.
