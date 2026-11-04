# Status & Error Codes

The HTTP Api exposed by the service exposes restful endpoints to offer its functionality. These endpoints are documented using the [OpenAPI specification](http://openapis.org/) and available for integrators to consult in the respective [API section](openapi.md).

In this section, we describe further the HTTP Status Codes that the service may return and the error information that accompanies them.

## Status Codes

The service makes use of the following subset of HTTP Status Codes:

* 200 OK - the request has succeeded
* 201 Created - the user was created
* 401 Unauthorized - the request lacks valid authentication credentials: the token is missing, malformed, expired, has an invalid signature or was issued by another issuer
* 403 Forbidden - the token is valid, but none of its audiences is allowed for this service
* 404 Not Found - the user, or the ORCID record, does not exist
* 409 Conflict - a user with the given id already exists
* 422 Unprocessable Content - the request does not match the expected model, or a given user id is not a valid UUID
* 502 Bad Gateway - an underpinning service (DMM or LLM) could not be reached, returned an error, or replied with unexpected output
* 503 Service Unavailable - the public keys needed to verify the token could not be fetched from the identity provider
* 500 Internal Server Error - an unexpected condition prevented the service from fulfilling the request

Authentication is checked first, so a request with a bad token gets a 401 or 403 regardless of anything else in it.

Errors returned by the ORCID public Api, other than 404, are passed on with the same status code.

## Error responses

Error responses follow the standard FastAPI format: a JSON object with a `detail` property. For all status codes except 422 caused by the request body, `detail` is a human readable message:

| Status | `detail` | Cause |
|---|---|---|
| 401 | `Missing bearer token` | No `Authorization: Bearer` header |
| 401 | `Invalid token` | Bad signature, wrong issuer, expired or malformed token |
| 403 | `Token missing required audience: one of user-profiler, query-recommender` | No allowed audience in the token |
| 404 | `No such user: '<user_id>'` | Unknown user |
| 404 | `ORCID profile not found: '<orcid_id>'` | Unknown ORCID iD |
| 409 | `User '<user_id>' already exists` | `POST /user/{user_id}` with an id already in use |
| 422 | `user_id must be a lowercase, hyphenated UUID` | `POST /user/{user_id}` with an invalid id |
| 502 | `The DMM could not be reached: ...` | Network error towards the DMM |
| 502 | `The DMM returned <status>: ...` | The DMM answered with an error, e.g. 401/403 if it rejects the forwarded token |
| 502 | `The DMM returned an unexpected response` | The DMM reply could not be parsed |
| 502 | `The LLM could not be reached or returned an invalid response` | The LLM call failed or its reply could not be parsed |
| 503 | `Could not fetch JWKS: ...` | The identity provider public keys are not reachable |

For example:

```json
{
    "detail": "No such user: '3f2e1d4c-0000-0000-0000-000000000000'"
}
```

## Validation errors

When the request body does not match the expected model, `detail` is a list with one entry per problem found. Each entry has a `loc` pointing at the problematic property, a `msg` describing the problem, a machine friendly `type` and the `input` that was received.

For example, creating a user without an email:

```json
{
    "detail": [
        {
            "type": "missing",
            "loc": ["body", "email"],
            "msg": "Field required",
            "input": { "name": "Alice", "surname": "Rossi", "affiliation": "University of Milan" }
        }
    ]
}
```

## Bad Gateway

A 502 means the request was valid and authenticated, but an underpinning service needed to serve it did not work as expected. It only concerns `generate-keywords` and `queries_test`, which depend on the DMM and, for the former, the LLM. For the DMM, the `detail` includes the status code it returned, which helps telling a rejected token (401/403) from an outage. For the LLM, the exact cause is logged by the service (see [Logging](logging.md)) but not returned to the caller. As LLM replies vary between calls, retrying may succeed.
