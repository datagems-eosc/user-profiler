# Quality Assurance

Key aspects of the Quality Assurance checklist that DataGEMS services must pass have been defined in the processes and documents governing the platform development and quality assurance. In this section we present a selected subset of these that are directly, publicly available.

## Reproducible builds

The service dependencies are pinned in the `uv.lock` file of the code repository, and the Docker image is built from that lock file (`uv sync --frozen`). Every published image is tagged with the version tag of the commit it was built from. See [Automations](automations.md).

## Input handling

All request bodies are validated against their models before they reach the database. Values written to the graph are escaped before being placed in GQL queries, so that user supplied text cannot alter the queries. User ids given by callers must be canonical UUIDs.

## Output validation

As keywords are produced by an LLM, the service does not trust its output. The LLM is asked to reply in a fixed JSON format, constrained with a JSON schema where the endpoint supports it. Every reply is then validated against that format, and the keywords are trimmed and de-duplicated before being returned. Replies that cannot be validated are reported to the caller as a 502 instead of being passed on. Generated keywords are only proposals: they are saved only when explicitly appended to the profile.

## Testing

The end to end example scripts in the [examples](https://github.com/datagems-eosc/user-profiler/tree/main/examples) folder exercise the endpoints against a local or deployed instance, starting from and returning to an empty database. They can be used as a smoke test, as shown in [Onboarding](onboarding.md).

The Streamlit interface described in [Onboarding](onboarding.md) can be used for manual, end to end testing, including the DMM and LLM integration.
