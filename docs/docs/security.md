# Security

Key aspects of the Security checklist and practices that DataGEMS services must pass have been defined in the processes and documents governing the platform development and quality assurance. In this section we present a selected subset of these that are directly, publicly available and affect the usage and configuration of the service.

## Authentication

All endpoints except the Api root (`GET /api/v1`) and the OpenAPI documentation require authentication using Bearer tokens in the form of JWTs (JSON Web Tokens). Clients must include a valid token in the Authorization header of each HTTP request, using the following format:

```
Authorization: Bearer <token>
```

The service only accepts JWTs issued by the trusted identity provider, the [DataGEMS AAI service](https://github.com/datagems-eosc/dg-aai). When a token is received, the service:

1. verifies the token signature with the public keys (JWKS) published by the issuer. Only `RS256` signatures are accepted
2. checks that the issuer *iss* claim matches the configured DataGEMS AAI realm
3. checks the expiration *exp* claim, to confirm the token is still valid
4. checks that the audience *aud* claim contains at least one of the allowed audiences. *aud* can be either a single string or a list

By default the allowed audiences are `user-profiler` and `query-recommender`. The second one is there because the Query Recommender forwards its caller's token to this service, and the DataGEMS Keycloak configuration does not add `user-profiler` to those tokens yet. It can be removed, through `OIDC_ALLOWED_AUDIENCES`, once it does.

Only if all these checks pass will the request be processed. A missing or invalid token results in `401 Unauthorized`, while a valid token issued for another service results in `403 Forbidden`. If the public keys cannot be fetched from the issuer, the service answers `503 Service Unavailable`. See [Status & Error Codes](error-codes.md).

The public keys are cached in memory for 5 minutes by default, so a key rotation at the issuer can take up to that long to be picked up.

You can check that a token is accepted by calling the `POST /api/v1/authtest` endpoint, described in the [Api Overview](api-overview.md).

The location of the configuration governing this behaviour is described in the relevant [Configuration](configuration.md) section.

## Authorization

There are currently no per-user permissions within the service. Any caller presenting a valid token with an allowed audience can read, create, edit and delete any profile. Access to the service should therefore be limited to trusted DataGEMS clients and services.

## Personal data

Full profiles (`GET /user/{user_id}`) include personal data, such as email and date of birth, and the user's query log. Services that only need to personalise their behaviour should use the portable profile (`GET /user/{user_id}/profile`), which leaves these out.

## Calls to other services

To extract keywords, the service reads the user's queries from the DMM on behalf of the caller, by forwarding the caller's access token as is. There is no token exchange: the token must also be accepted by the DMM, so its audience must include the DMM as well. If the DMM rejects the token, keyword generation answers 502 with the DMM status code.

The caller's token is never sent to the LLM endpoint, which is called with a dedicated service token, nor to ORCID, whose public Api needs no authentication.

## TLS towards the LLM endpoint

The service verifies the TLS certificate of the LLM endpoint against the system certificate authorities by default. This can be pointed to a specific CA bundle or certificate, or, for development against an endpoint with a self-signed certificate, disabled. Disabling verification prints a warning at startup. See [Configuration](configuration.md).

## Secrets

The LLM token is a secret and must be handled separately from the other configuration values. In the DataGEMS deployment it is kept in Vault and injected into the container as an environment variable. See [Configuration](configuration.md) and [Deployment](deployment.md).
