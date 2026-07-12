# my-datahub — Project Context for Claude

A personal home lab project exploring data engineering on a heterogeneous fleet:
Raspberry Pi ARM nodes, Zimaboard x86 nodes, TrueNAS servers, and GCP. Mixes
streaming and batch data sources, with Kubernetes (K3s) and Airflow as the core
compute substrate.

## Repo layout

- `ansible/` — playbooks and Jinja2 templates for provisioning and maintaining
  host assets (K3s nodes, Kafka brokers, load balancers, MariaDB, etc.).
- `k8s/` — Kubernetes manifests and Helm chart values (Fluent Bit ETL
  pipelines, Kafka UI, system-upgrade controller).
- `gcp/` — Terraform for GCP assets (Artifact Registry, IAM), BigQuery DDL, and
  Cloud Build config.
- `misc/` — utility scripts that aren't part of normal operations.

## Environments

Two parallel environments, with matching inventory files:

- **np (non-prod / test)** — `ansible/inventory.np.yaml`. VirtualBox VMs on a
  dev machine, used for trying out playbooks before they touch real hardware.
  Hostnames are `t`-prefixed (tkf01, tlb01, tk3s01, etc.).
- **pr (prod)** — `ansible/inventory.pr.yaml`. The real home lab. Pi cluster,
  Zimaboard Kafka nodes, HAProxy LBs, TrueNAS-backed MariaDB VMs, Harbor
  registry, Zabbix monitoring.

Playbooks should work against either inventory unchanged; pick the environment
with `-i inventory.np.yaml` or `-i inventory.pr.yaml`.

## Inventory group conventions

Groups are named by **function**, not technology, and plural where natural:

- `k8s` (parent) → `k8ctl` (control plane), `k8work` (workers)
- `kafka` — Kafka brokers (KRaft mode, SASL_PLAINTEXT + SCRAM-SHA-512)
- `lb` — HAProxy + Keepalived load balancers
- `databases` — relational databases and other data stores (currently MariaDB
  on `mdb1`/`mdb2`; named `databases` rather than `dbsys` or `rdms` to leave
  room for future engines without renaming)
- `registry` — Harbor container registry
- `zabbix` — monitoring server

Host vars worth knowing about:

- `ansible_host` — IP address (all hosts have a fixed IP)
- `architecture` — `aarch64` (Pi) or `x86_64` (Zimaboard, VMs)
- `rpi_model` — `pi4` or `pi5` (used by node selectors for Fluent Bit pods)
- `zagent: true` — install Zabbix agent on this host
- `kafka_is_controller: true` — this broker participates in the KRaft quorum
- `kafka_log_dirs` — list of data dirs for Kafka topic partitions
- `dbtype: mariadb` — engine type for hosts in the `databases` group
- `mariadb_role: primary` / `replica` — role assignment for HA pair

## Naming conventions

- **Playbooks**: `Setup_<Thing>.yaml` for first-run / bootstrap work,
  `Update_<Thing>.yaml` for ongoing maintenance. A `Setup_NewNode.yaml`
  master playbook imports the base set (users, packages, timezone, patching,
  mail, auditd, syslog forward, Zabbix agent) for any new node.
- **Templates**: Jinja2 templates live in `ansible/templates/` and use a
  `.j2` suffix. Numeric config-file prefixes (`50-forward.conf`,
  `90-kafka.conf`) match the rsyslog `/etc/rsyslog.d/` ordering convention.
- **Secrets**: `ansible/secrets.yaml` is gitignored. An
  `ansible/example.secrets.yaml` template is checked in with placeholder
  values; `mkexsec.sh` regenerates it from `secrets.yaml`. There are also
  per-environment variants (`secrets.pr.yaml`, `secrets.np.yaml`) for
  environment-specific credentials.

## Architecture highlights

### Networking and VIPs

The home network is `192.168.30.0/24` (pr) and `192.168.20.0/24` (np).
Floating VIPs managed by Keepalived on the `lb` group:

- `192.168.30.100` — K3s API (and HTTP/HTTPS ingress via NodePort backends)
- `192.168.30.101` — syslog ingest (TCP 514 → rsyslog → Kafka)
- `192.168.30.15` — MariaDB (MaxScale, deployed) managed on mdb1 and mdb2 not lb's.
  Running MariaDB **12.3 LTS** (upgraded from 11.8 via MariaDB's own apt repo,
  not Debian's default — see gotcha below).

HAProxy on each LB node fronts these VIPs. lb01 is the default master for the
K3s VIP; lb02 for the syslog VIP — spreads the active load.

### Observability pipeline

Two-stage syslog handling:

1. **All hosts** (`Setup_SyslogForward.yaml`) — rsyslog forwards
   security-relevant events (severity ≤ warning, auth/authpriv facilities,
   plus `area51gate` firewall) to the syslog VIP on TCP 514. Persistent
   on-disk queue in `/var/spool/rsyslog` for resilience.
2. **LB hosts** (`Setup_SyslogRelay.yaml`) — rsyslog receives those events,
   wraps them in a JSON envelope, and writes to Kafka topic
   `syslog-ingest-pr` via the omkafka module. Uses Confluent's librdkafka
   (≥ 2.4) because Debian's package has a SCRAM-SHA-512 incompatibility with
   Kafka 4.x.

A Fluent Bit pod (`k8s/fluentbit-etl/syslog/bq-writer/`) consumes that topic
and writes to BigQuery `cutlernet-datahub.privatena2.syslog_events`.

### Environmental sensors

ESP32/SHT15 sensors POST JSON to TCP 25000 on the K3s ingress VIP. HAProxy
load-balances to a NodePort (30025) → `envsense-receiver` Fluent Bit pod →
Kafka topic `envsensor-pr` → `envsense-bq-writer` pod → BigQuery
`cutlernet-datahub.publicna2.envsensor`.

Kafka is intentionally in the middle as a buffer for cloud/internet outages.

### Airflow — NFS-backed shared data volume

`datafiles-nfs-pv` / `datafiles-nfs-pvc` (namespace `airflow`) is a **static**
PV/PVC backed by a TrueNAS NFS export (`area51nas1:/mnt/datahub/datafiles`),
mounted at `/opt/airflow/datafiles` on scheduler, apiServer, and
KubernetesExecutor task pods. No CSI provisioner involved — plain kernel NFS
client, same mechanism whether it's a k3s pod, a dev laptop, or a NAS-side
cron job.

Identity model: the NFS export uses **Mapall** (User/Group both `datahub`,
UID 3002 / GID 3001). This rewrites *every* connecting client's identity to
that UID:GID server-side, regardless of what UID the client actually
presents — root on a laptop, an Airflow pod running as UID 50000, doesn't
matter. Confirmed working consistently across all three. This means pod
`securityContext.runAsUser` does **not** need to match 3002/3001 for the
mount to work — Mapall already guarantees it server-side. Dataset mode on
TrueNAS is `770`.

For SMB access to the same dataset (e.g. laptop on garden wifi, untrusted
network segment where NFS's IP-based trust is weaker), use SMB's "force
user/group" share option pointed at the same `datahub` identity, so both
protocols land on disk with consistent ownership.

### Kafka security

The pr cluster runs **KRaft mode** with:

- Broker port 9092: SASL_PLAINTEXT + SCRAM-SHA-512
- Controller port 9093: SASL_PLAINTEXT + PLAIN (PLAIN reads creds from JAAS,
  not the metadata log — avoids a startup deadlock where the
  StandardAuthorizer blocks VOTE messages before metadata is loaded)
- ACL-based authorization via `StandardAuthorizer`
- Three SCRAM users: an admin (super user), an RW producer user, an RO
  consumer user — seeded at storage-format time via `--add-scram`

Templates of interest: `kafka.server.properties.j2`,
`kafka_server_jaas.conf.j2`, `kafka.admin.properties.j2`.

There is also a legacy Pi-based Kafka cluster (`kafkaold` group in some
configs) being phased out; the new Zimaboard-based pr cluster (kf1–kf4) is
the canonical target.

## Known gotchas

- **Airflow's `apache-airflow/airflow` Helm chart (1.22.0) has no top-level
  `extraVolumes`/`extraVolumeMounts`.** Each component needs its own scoped
  copy: `scheduler.extraVolumes`, `apiServer.extraVolumes`,
  `workers.kubernetes.extraVolumes` (KubernetesExecutor — note the
  `workers.celery.*` / `workers.kubernetes.*` split as of a recent chart
  version; the old flat `workers.extraVolumes` is deprecated and silently
  ignored, not erroring). A top-level `extraVolumes:` key parses fine as
  YAML but does nothing — Helm just ignores it. Always verify a volume
  mount actually landed by checking the live pod spec
  (`kubectl get pod ... -o yaml | grep -A5 <volume-name>`), not just that
  `helm upgrade` succeeded without warnings.

- **MariaDB didn't support CTEs referenced from `DELETE` until version 12.3**
  (`MDEV-37220`, `WITH ... DELETE ... RETURNING`). Airflow 3.2.2's scheduler
  runs a periodic asset-cleanup query using exactly that construct — it ran
  on *every* DAG-processing cycle regardless of whether any DAGs/assets
  existed, so it crash-looped the scheduler with a 1064 syntax error even on
  a completely empty install. Confirmed root cause by reproducing the exact
  captured SQL directly against `mdb1` via the `mariadb` client. Fixed by
  upgrading MariaDB from 11.8 to 12.3 LTS via MariaDB's own apt repo
  (`mariadb_repo_setup` script, `--mariadb-server-version=mariadb-12.3` —
  Debian's default repo only ships 11.8 on trixie). If Airflow's scheduler
  ever crash-loops again with a `sqlalchemy.exc.ProgrammingError` / 1064 near
  a `DELETE`/`RETURNING`/CTE statement, suspect a MariaDB SQL-feature gap
  first, not application logic — MariaDB isn't in Airflow's own CI test
  matrix, so dialect-generation gaps like this can recur on future Airflow
  upgrades too.

- **`master_use_gtid` resets to default on a replica after a MariaDB major
  version upgrade** (e.g. 11.8 → 12.3). Must be manually re-applied
  post-upgrade (`CHANGE MASTER TO ... MASTER_USE_GTID=slave_pos` /
  `primary_use_gtid: replica_pos` in the `community.mysql` module) or
  replication silently falls back to non-GTID behavior. Not carried over
  automatically by the package upgrade.

- **PhotoPrism does not support PostgreSQL** (MariaDB/SQLite only, as of
  mid-2026 — Postgres support is on their roadmap with no committed date).
  Relevant if a "single shared database engine" plan for Airflow/Zabbix/
  PhotoPrism is ever revisited — Postgres-for-Airflow-only would mean running
  two separate DB engines rather than consolidating on one, since PhotoPrism
  forces the MariaDB/SQLite choice regardless.

## Conventions for changes

### When editing playbooks

- Stay idempotent. Most tasks should be safe to re-run; use `creates:` guards
  on shell commands that perform one-shot work (e.g., `kafka-storage.sh
  format`).
- Use `ansible.builtin.*` and `community.general.*` module FQCNs, not bare
  module names.
- Prefer `template:` over `lineinfile:` when a file is fully managed by
  Ansible; reserve `lineinfile:` for surgical edits to vendor-shipped configs.
- Handlers for service restarts: name them `restart <service>` or
  `Restart <Service>` and reference via `notify:`.
- Group filters in `hosts:` lines use `:` for union and `:!` for exclusion
  (e.g., `all:!registry`, `k8ctl:k8work`).

### When editing templates

- Keep the `# Ansible-managed: <purpose>` header comment at the top so it's
  obvious on the host that the file is generated.
- Pull credentials from `secrets.yaml` via `vars_files:`, never inline.
- For multi-environment templates, derive values from inventory rather than
  hardcoding (see how `kafka.server.properties.j2` builds `node.id` from the
  host's index in the kafka group).

### When editing Kubernetes manifests

- Pods that touch the Kafka pr cluster use `nodeSelector: hardware: pi4` (so
  network-bound Fluent Bit workloads land on Pi 4 nodes, leaving Pi 5s for
  compute).
- Kafka SASL credentials are injected via Kubernetes Secrets
  (`kafka-pr-cluster-sasl-producer`, `kafka-pr-cluster-sasl-consumer`) and
  surfaced as `${KAFKA_USER}` / `${KAFKA_PW}` env vars in Fluent Bit configs.
- GCP service account credentials live in a Secret named `gcp-bq-credentials`
  (never committed).

### When editing Terraform / GCP

- Backend is GCS bucket `cutlernet-datahub-tf-state`. State is shared; don't
  run `terraform apply` locally — Cloud Build does it on commit to `main`
  (see `gcp/cloudbuild.yaml`).
- Project ID: `cutlernet-datahub`. Region: `northamerica-northeast2`.

## Current work in progress

### MariaDB HA pair — done, superseded by Architecture highlights above

The planning notes that used to live here (VIP `192.168.30.10`, MaxScale,
playbook layout) are superseded: the pair is live on `mdb1`/`mdb2` at VIP
`192.168.30.15`, now running MariaDB 12.3 LTS. Datadir ended up on a
dedicated NVMe (`mdb1`: Kingston NV2 1TB at `/var/lib/mysql`, `noatime`) —
the "bind-mount vs default path" question is resolved in favor of a
dedicated volume, as originally leaned toward. MaxScale placement (dedicated
VM vs `lb` hosts) is still genuinely open if/when that layer gets built.

### Next up

- Zabbix migration to dedicated M75q-1 Tiny node, targeting mdb1/mdb2 for
  its externalized DB (see Zabbix intentionally running outside k3s per the
  control-plane-independence principle).
- `apache-airflow-providers-google` via custom Harbor-hosted image.
- ArgoCD for GitOps sync from `k8s/`.

## How to be useful in this repo

- **Default to playbook-first.** This repo's primary deliverables are Ansible
  playbooks and the Jinja2 templates they render. Prefer adding to that
  surface area over one-off scripts.
- **Match existing patterns** for new playbooks: header comment block, FQCN
  module names, `vars_files: [secrets.yaml]` if secrets are needed, handlers
  at the bottom.
- **Test-first inventory.** When a new playbook is being written, target
  `inventory.np.yaml` first. Promotion to pr happens once it's been validated
  on the VMs.
- **Surface assumptions explicitly.** If something is going to require a new
  group, new host var, or new secret, call it out so the inventory and
  `example.secrets.yaml` can be updated at the same time.
- **No silent changes to live infrastructure.** `ansible-playbook` without
  `--check` should always be a deliberate, reviewed action — never something
  that runs automatically as part of an agent's "fix" loop.