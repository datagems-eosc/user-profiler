# Data Stores

The service is the owner of the DataGEMS user profiles, so unlike a pure gateway it keeps state of its own.

## Graph database

Profiles are stored in [Grafeo](https://grafeo.dev), an embedded property graph database queried with GQL. "Embedded" means the database runs inside the service process and keeps its data in a local folder, set with `GRAFEO_DB_PATH` (`./grafeo_data` by default). There is no separate database server to run.

The structure of the graph is defined by the PG-schema in [`schema/user_model.pg`](https://github.com/datagems-eosc/user-profiler/blob/main/schema/user_model.pg) and summarised in the [Architecture](architecture.md).

The database is opened when the service starts and flushed and closed when it shuts down, for example when Kubernetes stops the pod.

## Persistence

As the data lives in a local folder, that folder must survive restarts. In Kubernetes it must be on a persistent volume: the DataGEMS deployment mounts the `user-profiler-pvc` volume on `/data` and sets `GRAFEO_DB_PATH=/data/grafeo_data`. Without a persistent volume, every redeploy starts with no users.

Because only one process can safely use the database folder at a time, the service must run as a **single replica**, and updates must stop the old pod before starting the new one (the `Recreate` deployment strategy). See [Deployment](deployment.md).

## How profiles are written

Writes rewrite the whole user subgraph: the existing User node and everything connected to it is deleted, then the updated profile is written again. This keeps the graph consistent with the profile model, but means that two concurrent writes to the same user can overwrite each other: the last one wins.
