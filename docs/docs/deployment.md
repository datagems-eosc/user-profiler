# Deployment

The service is part of the DataGEMS platform offered through an existing deployment, following the DataGEMS release and deployment procedures over a managed infrastructure. The purpose of this section is not to detail the deployment processes put in place by the DataGEMS team, but to give an overview of what the service needs to run.

## Docker

The service is offered as a Docker image through the DataGEMS GitHub Organization Packages, as `ghcr.io/datagems-eosc/datagems-eosc/user-profiler:<version>`. This process is described in the relevant [Automations](automations.md) section.

The image is based on `python:3.12-slim`, installs the locked dependencies with [uv](https://docs.astral.sh/uv/) (without the development tools, such as Streamlit) and starts the Api with uvicorn on port `5000`. Mount a volume for the database folder, otherwise the users are lost when the container is removed:

```bash
docker run -p 5000:5000 \
  -v user-profiler-data:/data \
  -e GRAFEO_DB_PATH=/data/grafeo_data \
  -e LLM_API_URL="https://chat.scayle.es/api/chat/completions" \
  -e LLM_MODEL_LIST="https://chat.scayle.es/api/models" \
  -e LLM_TOKEN="your-llm-token" \
  ghcr.io/datagems-eosc/datagems-eosc/user-profiler:<version>
```

## Kubernetes

In the DataGEMS development cluster the service runs in the `univr` namespace, as:

* a **Deployment** `user-profiler` with a **single replica** and the **`Recreate`** strategy, as the embedded database can only be used by one process at a time (see [Data Stores](datastore.md)). It has a readiness probe on TCP port 5000 and resource limits of 500m CPU and 2Gi memory
* a **PersistentVolumeClaim** `user-profiler-pvc`, mounted on `/data`, holding the database (`GRAFEO_DB_PATH=/data/grafeo_data`)
* a **ClusterIP Service** `user-profiler-service` on port 5000, which is how other services in the cluster, such as the Query Recommender, reach it
* an **Ingress** and an **HTTPRoute** exposing `https://datagems-dev.scayle.es/up/...`, stripping the `/up` prefix (`ROOT_PATH` is set to `/up` accordingly), with request timeouts raised to 300 seconds to leave room for keyword generation
* a **VaultStaticSecret** that syncs the `LLM_TOKEN` from Vault into the `user-profiler-secrets` Kubernetes secret

The manifests are maintained in the deployment repository of the service.

## Configuration

In order for the service to operate properly, the needed configuration values must be set to match the environment that it must operate in. The needed configuration is described in the relevant [Configuration](configuration.md) section.

## Dependencies

For the service to be able to operate, its underpinning services must be available and accessible:

* the DataGEMS AAI, to verify tokens. Without it, authenticated calls fail with 503
* a persistent volume for the database. Without it, users are lost at every redeploy
* the DMM and the LLM endpoint, to generate keywords. Without them, keyword generation fails with 502, while every other endpoint keeps working
* the ORCID public Api, to fetch ORCID records. Only `GET /orcid/{orcid_id}` depends on it

The [Architecture](architecture.md) section describes the ecosystem in which the service needs to operate.
