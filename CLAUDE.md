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
- `192.168.30.10` — MariaDB (MaxScale, planned)

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

### MariaDB HA pair (next)

Planning a primary/replica MariaDB pair across `mdb1` and `mdb2` in the
`databases` group, GTID-based async replication, eventual MaxScale front end
on VIP `192.168.30.10`, eventual Keepalived float between LBs.

Playbook layout decided:

- `Setup_MariaDB_Common.yaml` — apt install, base `my.cnf`, datadir, firewall,
  server_id. Runs on both hosts in the `databases` group.
- `Setup_MariaDB_Primary.yaml` — primary-specific config (log_bin, GTID,
  binlog_format), replication user creation, mysqldump with `--master-data`.
- `Setup_MariaDB_Replica.yaml` — primary-specific config (read_only,
  relay logs), restore the primary dump, `CHANGE MASTER ... MASTER_USE_GTID`,
  `START REPLICA`.
- `Setup_MariaDB_HA.yaml` — wrapper that imports the three above in order.

Role assignment is by explicit host var (`mariadb_role: primary` / `replica`)
rather than positional, for clarity. Testing happens against `inventory.np.yaml`
(mdb1/mdb2 in np) before promotion to pr.

Templates planned: `mariadb.server.cnf.j2` (shared base),
`mariadb.primary.cnf.j2` (binlog/GTID), `mariadb.replica.cnf.j2`
(read_only, relay log settings).

Secrets needed in `secrets.yaml`:

- `mariadb_root_pw`
- `mariadb_repl_user`, `mariadb_repl_pw` (the replication account)
- Possibly `mariadb_maxscale_user`, `mariadb_maxscale_pw` later

### Open architectural questions

- Whether to bind-mount the datadir to a separate volume on mdb1/mdb2 or use
  the default `/var/lib/mysql`. Probably separate volume to make future
  TrueNAS-backed storage cleaner.
- Whether the eventual MaxScale layer should run on the existing `lb` hosts
  or new dedicated VMs. Leaning toward dedicated, to keep the LB tier
  single-purpose.

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