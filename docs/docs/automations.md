# Automations

A number of automations are available to facilitate the development, deployment and documentation of the service. Here we describe the ones that are directly, publicly available.

## Dockerfile

The main delivery package for the service is a docker image. The [Dockerfile](https://github.com/datagems-eosc/user-profiler/blob/main/Dockerfile) at the root of the code repository builds the Docker image. Dependencies are installed with [uv](https://docs.astral.sh/uv/) from the committed `uv.lock`, so the image always contains the exact dependency versions that were tested. Development tools, such as Streamlit, are left out of the image.

## Docker image publishing

A GitHub Action workflow is available to [build and publish](https://github.com/datagems-eosc/user-profiler/blob/main/.github/workflows/docker-image.yml) the docker image for the service. The action is triggered when a new tag matching `v*` is pushed to the repository. This way, all the images produced are always named and can be traced back to the codebase snapshot that generated them.

The generated docker image is pushed to the GitHub organization Packages using the name of the service repo and the version tag that triggered the execution.

## Documentation

A GitHub Action workflow is available to [generate the documentation](https://github.com/datagems-eosc/user-profiler/blob/main/.github/workflows/deploy-docs-on-demand.yml) presented here. The action is triggered manually and runs against the selected branch of the repository. The documentation generated is versioned and the documentation version is expected as input to the workflow.

The documentation is built using the [mkdocs](https://www.mkdocs.org/) library and specifically using the [Material for mkdocs](https://squidfunk.github.io/mkdocs-material/) theme. A number of additional tools are utilized, such as [mike](https://github.com/jimporter/mike) to support versioning and [neoteroi.mkdocsoad](https://www.neoteroi.dev/mkdocs-plugins/web/oad/) to support OpenAPI specification rendering.

The documentation is generated and tagged with the provided version, which is also aliased as `latest`. It is pushed to the `gh-pages` branch, which the repository GitHub Page presents its contents from. The branch is created by the first run if it does not exist yet.

The [OpenAPI Reference](openapi.md) is rendered from the `openapi.json` file kept with the documentation. When the Api changes, this file should be refreshed from a running instance (`/api/v1/openapi.json`) before publishing a new documentation version.
