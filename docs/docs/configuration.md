# Configuration

The service is configured entirely through environment variables. They are read once, when the service starts, so any change requires a restart.

## Environment variables

### Data store

| Variable | Default | Description |
|---|---|---|
| `GRAFEO_DB_PATH` | `./grafeo_data` | Folder of the embedded Grafeo database holding all users. In Kubernetes it must be on a persistent volume, see [Data Stores](datastore.md) |

### Keyword ageing

| Variable | Default | Description |
|---|---|---|
| `KEYWORD_HALF_LIFE_DAYS` | `30` | Days for a session keyword's weight to halve |
| `KEYWORD_MIN_WEIGHT` | `0.1` | Below this weight a keyword expires and is left out of the portable profile (about 100 days with the default half-life) |
| `ORCID_KEYWORD_WEIGHT` | `0.5` | Constant weight of ORCID keywords |

See [Keyword ageing](architecture.md#keyword-ageing).

### LLM

| Variable | Default | Description |
|---|---|---|
| `LLM_API_URL` | *(none)* | Full URL of the OpenAI-compatible chat completions endpoint, e.g. `https://chat.scayle.es/api/chat/completions` |
| `LLM_TOKEN` | *(none)* | Bearer token used to call the LLM endpoint. This is a secret |
| `LLM_MODEL_LIST` | *(none)* | URL listing the models available at the LLM endpoint, e.g. `https://chat.scayle.es/api/models`. If it is not set or cannot be reached, the preferred model name is used as is |
| `LLM_SSL_VERIFY` | `true` | TLS certificate verification for the LLM endpoint. `true` verifies against the system CAs, a file path verifies against that CA bundle or certificate, `false` disables verification (for an endpoint with a self-signed certificate). With `false`, the service prints a warning at startup |

The LLM is only needed by `GET /user/{user_id}/generate-keywords`. If these variables are not set, every other endpoint still works.

The preferred model is `kimi-k2.6`. The service checks it against the model list and falls back to the first available model if it is not offered. The preferred model is currently set in code, not through configuration.

### DMM

| Variable | Default | Description |
|---|---|---|
| `DMM_URL` | `https://datagems-dev.scayle.es/dmm` | Base URL of the Data Model Management service, where the users' queries are read from. In the DataGEMS cluster this is `http://data-model-management-service:5000` |
| `MOCK_DMM` | *(unset)* | Development only. When set to `1`, queries are read from a local `mock_aplog.json` file instead of the DMM |

### Authentication

| Variable | Default | Description |
|---|---|---|
| `OIDC_ISSUER_URL` | `https://datagems-dev.scayle.es/oauth/realms/dev` | The expected token issuer (*iss* claim), i.e. the DataGEMS AAI realm |
| `OIDC_JWKS_URL` | `{OIDC_ISSUER_URL}/protocol/openid-connect/certs` | Where the issuer public keys are fetched from |
| `OIDC_CLIENT_ID` | `user-profiler` | The client id of this service |
| `OIDC_ALLOWED_AUDIENCES` | `{OIDC_CLIENT_ID},query-recommender` | Comma separated list of audiences: a token is accepted if its *aud* claim contains any of them |
| `JWKS_CACHE_TTL_SECONDS` | `300` | How long the public keys are cached, in seconds |

See [Security](security.md) for how these are used.

### Http

| Variable | Default | Description |
|---|---|---|
| `ROOT_PATH` | *(empty)* | The path prefix under which a reverse proxy exposes the service, e.g. `/up`. It is used so that the generated OpenAPI document and the Swagger UI work behind the proxy. The proxy is expected to strip the prefix before forwarding requests |

The Docker image listens on port `5000`. When started locally with `uvicorn up_api.main:app`, the default port is `8000`.

## Example

```bash
export LLM_API_URL="https://chat.scayle.es/api/chat/completions"
export LLM_MODEL_LIST="https://chat.scayle.es/api/models"
export LLM_TOKEN="your-llm-token"
uvicorn up_api.main:app --reload
```

```powershell
$env:LLM_API_URL = "https://chat.scayle.es/api/chat/completions"
$env:LLM_MODEL_LIST = "https://chat.scayle.es/api/models"
$env:LLM_TOKEN = "your-llm-token"
uvicorn up_api.main:app --reload
```

When working against an LLM endpoint with a self-signed certificate, save the endpoint's certificate once and point `LLM_SSL_VERIFY` to it, rather than disabling verification:

```bash
openssl s_client -connect <llm-host>:<port> </dev/null 2>/dev/null | openssl x509 > llm.pem
export LLM_SSL_VERIFY="$PWD/llm.pem"
```

## Secrets

`LLM_TOKEN` is the only secret the service needs. It should not be stored alongside the other configuration values. In the DataGEMS deployment it is kept in Vault and exposed to the container through a Kubernetes secret, as described in [Deployment](deployment.md).
