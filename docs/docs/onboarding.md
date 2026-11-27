# Onboarding Material

This section contains some references and material that will assist users and integrators onboarding process.

## References

The definite guide for integrators remains the service [OpenAPI Reference](openapi.md).

The codebase is available under the [MIT License](license.md) in our [GitHub code repository](https://github.com/datagems-eosc/user-profiler).

To get a better understanding of the endpoints and their payloads, you can read the [Api Overview](api-overview.md).

To know more about Api response codes and how to interpret them, you can take a look at the [Status & Error Codes](error-codes.md).

On aspects pertaining to security, you can read more at the [Security](security.md) section.

For an overall view of the service, you can go through the [Architecture](architecture.md).

For any questions, you can consult the [FAQ](faq.md).

If you are facing a problem, check if there is a relevant [issue](https://github.com/datagems-eosc/user-profiler/issues) answering your question.

You can always contact us through the [DataGEMS Help Desk](https://datagems.eu/contact-us/).

## Running locally

The service requires Python 3.12 or later. With [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/datagems-eosc/user-profiler.git
cd user-profiler
uv sync
uv run uvicorn up_api.main:app --reload
```

The Api is then available at `http://localhost:8000`, with the Swagger UI at `http://localhost:8000/api/v1/swagger`. The database is created in `./grafeo_data`. To extract keywords, set the LLM and DMM variables described in [Configuration](configuration.md).

## Examples

Ready-to-run scripts that exercise the endpoints end to end are in the [examples](https://github.com/datagems-eosc/user-profiler/tree/main/examples) folder of the code repository, for bash (`api_examples.sh`) and PowerShell (`api_examples.ps1`). They start from an empty database, create two users, run through the operations, and delete both users so the database is clean at the end.

```bash
bash examples/api_examples.sh
```

```powershell
.\examples\api_examples.ps1
```

All endpoints except the Api root need an `Authorization: Bearer <token>` header, with an access token retrieved from the DataGEMS AAI service with `user-profiler` (or `query-recommender`) in its audience. For example:

```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/users
```

## User interface

The code repository includes a [Streamlit](https://streamlit.io/) interface for testing, `app.py`, with one module per tab in `ui_local/tabs/`:

```bash
uv sync                      # Streamlit is a development dependency
uv run streamlit run app.py
```

In the sidebar you choose the Api to use (local, the DataGEMS development instance, or local with DMM mode) and paste the Keycloak access token, which can also be provided through the `DATAGEMS_TOKEN` environment variable. The interface warns when the token is missing or expired.

It has four tabs. Only the selected one runs, so the hidden tabs make no Api calls:

* **Users**: list, create, edit and delete users. When creating or editing a user, ORCID data can be fetched from ORCID by iD. A user's page shows their location, keywords, ORCID data and sessions, and lets you generate keywords and **Accept & save** the new ones
* **Chat**: pick a user and type queries as they would. Queries are recorded in a session, which is closed after 5 minutes of inactivity
* **DMM queries**: look up the queries the DMM has logged for a user id, or the most recent queries by any user. Useful to find which user id a query was logged under
* **UI demo**: a mock of the profile settings page of the DataGEMS user interface, for its developers. It only calls the `/user/me` endpoints, as the user of the token in the sidebar: it shows the profile, edits it, shows the keywords with their status, and offers to create the profile if it does not exist yet

With **Local + DMM** selected, the **Users** tab also lets you add a DMM user to the local database and run a keyword refresh from the DMM.

## Tutorials

You can find useful material and onboarding guidelines in our social channels below, as well as our [platform documentation](https://datagems-eosc.github.io/).

## Keep in touch

Make sure to follow the DataGEMS channels to get the latest news and references:

* [GitHub](https://github.com/datagems-eosc/)
* [Instagram](https://www.instagram.com/datagems_eosc)
* [X](https://x.com/datagems_eosc)
* [YouTube](https://www.youtube.com/@DataGEMS-65n)
* [LinkedIn](https://www.linkedin.com/company/eosc-datagems)
* [Facebook](https://www.facebook.com/datagems.eosc/)
