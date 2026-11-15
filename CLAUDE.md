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
- `images/` — Dockerfiles and source for custom container images we build and
  push to Artifact Registry (`images/mcp-readonly/` so far). `k8s/` references
  these images but never builds them.
- `misc/` — utility scripts that aren't part of normal operations, plus
  "pre-Ansible" bootstrap scripts (see below).

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
  on `mdb1`/`mdb3`; named `databases` rather than `dbsys` or `rdms` to leave
  room for future engines without renaming)
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
- `192.168.30.15` — MariaDB (MaxScale, deployed) managed on mdb1 and mdb3 not lb's.
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

`datafiles-nfs-pv` / `datafiles-nfs-pvc` and `airflow-dags-nfs-pv` /
`airflow-dags-nfs-pvc` (namespace `airflow`) are **static** PV/PVCs backed by
TrueNAS NFS exports on `area51nas1` (`192.168.30.9`):
`/mnt/share/datahub/datafiles` and `/mnt/share/datahub/airflow-dags`
(manifests: `k8s/charts/airflow/nfs-datafiles.yaml`,
`k8s/charts/airflow/nfs-airflow-dags.yaml`). Mounted at
`/opt/airflow/datafiles` / `/opt/airflow/dags` on scheduler, apiServer,
dag-processor, triggerer, and KubernetesExecutor task pods. No CSI
provisioner involved — plain kernel NFS client, same mechanism whether it's a
k3s pod, a dev workstation, or a NAS-side cron job.

**Paths changed 2026-11-15** when `area51nas1`'s hostname/VIP role moved to
new hardware (see "area51nas1 hardware migration" under Current work in
progress below) — old paths were `/mnt/datahub/datafiles` and
`/mnt/datahub/airflow-dags`. A client with a pre-existing kernel NFS mount at
the old path will hit `Stale file handle` after the cutover; `umount -f` (or
`-l` if that hangs) and remount — editing `/etc/fstab` alone does not fix an
already-mounted filesystem.

Identity model: the NFS export uses **Mapall** (User/Group both `datahub`).
On the new host this is UID **3001** / GID **3001** (the old host used UID
3002 / GID 3001 — not reconciled, since Mapall maps by account *name* on the
server, not by matching numeric IDs between client and server, so this
doesn't affect functionality). This rewrites *every* connecting client's
identity to that UID:GID server-side, regardless of what UID the client
actually presents — root on a laptop, an Airflow pod running as UID 50000,
doesn't matter. This means pod `securityContext.runAsUser` does **not** need
to match the NAS-side UID/GID for the mount to work — Mapall already
guarantees it server-side. Dataset mode on the new host is `775` (group *and*
other both get read/execute — intentionally left permissive since this is
public, non-sensitive data; tighten to `770` if that ever changes).

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

- **TrueNAS 25.10 "Goldeye" removed the internal Certificate Authority
  signing engine and its UI entirely** (Credentials → Certificates page has
  no CA card/section anymore — this is expected, not a bug) **and removed
  the built-in SMART test scheduling UI/service** (`smartmontools` is still
  installed and TrueNAS still does some background SMART polling, but
  scheduled tests now need a manual cron job, e.g. `smartctl -t short
  /dev/sdX`, or a third-party app like Scrutiny). A host still on an older
  SCALE version (e.g. 25.04.2.6) will have both of these in its UI; don't
  assume feature parity across hosts without checking the version first —
  see the area51nas1 hardware migration note above for a concrete case
  where this caused confusion.

- **`mcp-gate01` is dual-homed and replies to other home networks leave via
  the wrong port.** `eth0` is the TELUS Fibe LAN (`192.168.1.0/24`, DHCP
  default, metric 100); `eth1` is the lab (`192.168.30.0/24`, static default
  via `.30.1`, metric 101). Linux routes on destination only, so replies to
  a client outside `.30` (laptop on `.40`, office `.20`, wired `.10`) match
  the lower-metric TELUS default, leave `eth0`, and the Fibe router drops
  them as unsolicited WAN-side packets. Symptom: ping/ssh from a `.30` host
  works, from other subnets times out; tcpdump shows the request In on `eth1`
  and the reply Out on `eth0`. Fix is a static return route per client
  network via `192.168.30.1` on `eth1` (stored in the NetworkManager profile
  so it survives reboot). A new dual-homed host, or a new client subnet
  that needs to reach it, needs the same treatment — edit `NETWORKS` in
  `misc/mcpgate_routes.sh` and re-run it. Traffic between zones is then
  logged at the central home router.

## Pre-Ansible bootstrap scripts

Some setup has to exist before Ansible can reach a host at all (network
reachability, return routes, fixed IPs). Ansible can't repair its own control
path, so these are **standalone bash scripts in `misc/`, run on the target host
itself** (console or via a jump host), not playbooks. Pattern, from
`misc/mcpgate_routes.sh`:

- Header comment explaining the problem, why it isn't a playbook, and where to
  run it.
- A `# --- Configuration ---` block at the top for the values that change.
- Idempotent and re-runnable: check current state before changing it, look up
  NetworkManager profiles by device rather than auto-generated names.
- Print the resulting state at the end so the run is self-verifying.

This makes the script the record of what was done and the recipe for
replacing the node. Use this pattern for future pre-Ansible installs;
`Setup_FixedIP.yaml` is the existing in-repo precedent for the bootstrap
layer.

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

### area51nas1 hardware migration — done (2026-11-15)

The original `area51nas1` (AM4 Ryzen box) had a recurring hard-lockup fault
(suspected CPU/socket damage from an earlier CPU swap). Its role was handed
off to new NAS hardware rather than repaired in place:

- New hardware took over the `area51nas1` hostname and production VIP
  `192.168.30.9`. It runs **TrueNAS 25.10.8 "Goldeye"**.
- The original box was renamed `area51nas2` and moved to `192.168.30.8` — it
  is now the backup/bench-test NAS, pending hardware diagnosis/repair. It
  still runs **TrueNAS 25.04.2.6** (see the Goldeye UI-removal gotcha below —
  the two hosts' Certificates/Credentials pages look different because of
  this version gap, not a config error).
- Airflow's NFS shares were recreated fresh on the new host rather than
  copied (`/mnt/share/datahub/{datafiles,airflow-dags}`, new ZFS datasets,
  `datahub` identity UID/GID 3001/3001, mode `775`) — see the Airflow NFS
  section above for the full identity/path details. No data was migrated
  from the old `/mnt/datahub/*` datasets.
- The old host's TLS setup (`jeffc-homelab-ca` self-signed CA +
  `area51nas1-webui` leaf cert) was **not** carried over — TrueNAS 25.10
  removed the CA-signing UI entirely (see gotcha below), so there was nothing
  to import it into. The new host's web UI runs on the default self-signed
  `truenas_default` cert (browser warning accepted) until it's switched to
  Let's Encrypt. Not a priority fix.
- **Still outstanding:** `mcp-server` namespace's `mcp-datafiles-nfs-pv`
  (see the Read-only MCP gateway section below) still points at the old
  `192.168.30.9:/mnt/datahub/datafiles` path and needs the same path update
  whenever that project resumes.

### MariaDB HA pair — done, superseded by Architecture highlights above

The planning notes that used to live here (VIP `192.168.30.10`, MaxScale,
playbook layout) are superseded: the pair is live on `mdb1`/`mdb2` at VIP
`192.168.30.15`, now running MariaDB 12.3 LTS. Datadir ended up on a
dedicated NVMe (`mdb1`: Kingston NV2 1TB at `/var/lib/mysql`, `noatime`) —
the "bind-mount vs default path" question is resolved in favor of a
dedicated volume, as originally leaned toward. MaxScale placement (dedicated
VM vs `lb` hosts) is still genuinely open if/when that layer gets built.

### Read-only MCP gateway — Claude connected, Gemini parked (as of 2026-11-15)

**Design (current; supersedes both the dual-homed `mcp-gate01` approach and a
later tailscale-operator/CRD approach that was also abandoned).** Claude
reaches a read-only MCP server through **Tailscale Funnel**, run entirely
inside K3s, with **no Kubernetes operator involved**:

    Internet → https://mcp-funnel.tailf30707.ts.net (Tailscale Funnel)
             → mcp-funnel pod (ns: tailscale, tag:mcp-edge, manual authkey)
             → mcp-server.mcp-server.svc:8000 (plain cluster networking)
             → mcp-server pod (ns: mcp-server)

- The `tailscale-operator` Helm install and `k8s/mcp/60-funnel-ingress.yaml`
  (CRD-based Ingress) were abandoned mid-project: the operator's own
  OAuth-based self-tagging (minting an authkey for `tag:k8s-operator`) is
  rejected by this tailnet's control plane with a 400 "invalid or not
  permitted" error — reproduced across three separate OAuth clients, two
  browsers (including a non-automated one), and multiple `tagOwners`
  configurations. A human-generated authkey for the *same* tag works fine,
  which is the mechanism `mcp-funnel` uses instead: it joins the tailnet
  exactly like any other device (phone, laptop), just with `tag:mcp-edge`
  attached, via a manually-generated reusable/non-ephemeral key. No Tailscale
  support ticket has been filed (free plan; decided against it) — this is
  logged as a known, unresolved platform/account quirk, not worth chasing
  further. `k8s/tailscale-operator/` and `60-funnel-ingress.yaml` are dead
  code, kept only as a record of what didn't work.
- Namespaces: `tailscale` (now just `mcp-funnel`; baseline PSS) and
  `mcp-server` (the MCP pod; restricted PSS). Both default-deny via
  NetworkPolicy; `mcp-funnel` may reach only `mcp-server:8000`; `mcp-server`
  accepts ingress only from `tailscale`. These NetworkPolicy rules are
  namespace-wide (`podSelector: {}`), written generically enough that they
  needed zero changes when the operator was dropped for a plain Deployment.
- `mcp-funnel`'s tailscale container auto-detects Kubernetes and stores its
  tailnet state in a Secret (not just a file), regardless of `TS_STATE_DIR` —
  needs its own scoped ServiceAccount/Role (`get/create/update/patch` on one
  named Secret; `create` can't be scoped by `resourceNames`, needs its own
  unscoped rule). See `k8s/mcp/55-funnel-standalone.yaml`.
- The MCP server (`images/mcp-readonly/`, FastMCP, streamable HTTP :8000,
  per-client bearer tokens `MCP_TOKEN_<NAME>`) offers read-only tools for the
  k8s API, MariaDB (mdb3 replica `192.168.30.16`), Kafka (metadata + bounded
  message reads), and the NFS datafiles share (names/metadata only).
  `mcp` is pinned `<2` (v2 renamed `FastMCP`).
- Manifests: `k8s/mcp/` (apply order and secrets in its README, which still
  describes the old operator-based order — needs a rewrite to match this
  section).

**Done**
- Image built/pushed, deployed, verified end-to-end — both internally
  (`kubectl port-forward`) and from the real internet through the public
  Funnel URL (`curl` from an external host): 401 without a token, full MCP
  `initialize` handshake with one, `tools/list` returns all 11 tools.
- NFS PV/PVC repointed to the post-migration path
  (`192.168.30.9:/mnt/share/datahub/datafiles`); old PV/PVC deleted and
  recreated (server/path are immutable on a live PV).
- Secrets live: `operator-oauth` (unused now, harmless to leave or delete),
  `mcp-mariadb`, `mcp-kafka` (using the existing shared `dhconsume` consumer
  user — a deliberate choice over a dedicated Kafka principal, made after the
  operator/OAuth saga; revisit only if isolation from other `dhconsume`
  consumers ever matters), `mcp-tokens` (fresh `MCP_TOKEN_CLAUDE`/
  `MCP_TOKEN_GEMINI`, generated and piped straight into the Secret without
  ever being printed), `mcp-funnel-authkey`.
- MariaDB: `mcp_ro`@`192.168.30.%` granted `SELECT, SHOW VIEW` on `airflow`
  and `photoprism` only (not `jeffc` — deferred, easy to add later; never
  `mysql`, which holds every account's password hash in
  `mysql.global_priv`/`mysql.user`). Confirmed replicated to mdb3. **Open
  risk, not yet decided:** `airflow.connection` holds other systems' stored
  credentials and is covered by the schema-level grant — no table-level
  `REVOKE` has been applied, and the MCP tool doesn't filter it at the
  application layer either. `db_query`/`db_schema` are left on "Needs
  approval" in Claude's connector settings partly to mitigate this.
- Claude connector ("Home Lab k8s") registered and working: custom connector,
  **"No sign-in"** auth mode (not OAuth — Claude's UI auto-detects an OAuth
  flow from the `WWW-Authenticate: Bearer` 401 response and defaults to the
  wrong mode), `Authorization: Bearer <MCP_TOKEN_CLAUDE>` as a static request
  header. Tool-level approval set to "Needs approval" across the board for
  now.

**Gemini — parked, needs OAuth work**
Gemini's custom MCP connector (gemini.google.com → Settings → Connected Apps
→ Custom apps, reached via Developer mode) is **OAuth-only** — confirmed live:
it auto-detects our server lacks Dynamic Client Registration and only offers
a "Client ID"/"Client secret" fallback, no static API-key/header option like
Claude has. `mcp-readonly` doesn't implement OAuth at all today.

Planned approach when this gets picked up: reuse **Google's own OAuth 2.0
infrastructure** as the authorization server instead of writing our own
`/authorize`+`/token` endpoints —
1. Create an OAuth 2.0 Client ID (Web application) in GCP Console, in
   `cutlernet-datahub`, redirect URI from Gemini's "Copy redirect URI".
2. `mcp-readonly` gains token-validation logic: verify the incoming Bearer
   token is a genuine Google-issued ID token (signature against Google's
   JWKS, `aud` matches our Client ID, `email` claim matches the account
   owner) instead of a static per-client secret.
3. **Manage the OAuth Client ID as Terraform** in `gcp/` (not click-ops in
   the Console), deployed via the existing Cloud Build pipeline on commit to
   `main` — same pattern already used for Artifact Registry/IAM, and the
   pattern used at $DAYJOB worth carrying over here deliberately.
4. Untested assumption to verify before trusting this plan: that Gemini's
   connector flow actually cooperates with Google's token/discovery
   semantics for a resource that isn't a Google API. Plausible (Google's
   OAuth endpoints support PKCE/OIDC discovery), not proven.

**Still to do / redo**
1. Decide on `airflow.connection` (table-level REVOKE vs. app-layer filter)
   — see "Open risk" above.
2. Gemini OAuth work, see above — not started.
3. Verify node pulls from `datahub-pr` under real (non-manual) conditions;
   confirm allow-rule NetworkPolicies work once more pods are added (only
   default-deny + the two active allow rules have been proven so far).
4. Commit the new/changed files (`images/`, `k8s/mcp/` incl. the new
   `55-funnel-standalone.yaml`, reverted `k8s/tailscale-operator/values.yaml`,
   dead `60-funnel-ingress.yaml`) — holding on this per request, user is
   committing manually at the end of the session.
5. Rewrite `k8s/mcp/README.md`'s apply order, which still describes the
   abandoned operator-based flow.
6. Optional: kubeconfig fallback in `tools_k8s.py` so the image runs outside
   a cluster (e.g. on the dev station); consider a read-only NFS export on
   TrueNAS (current read-only is client-side only, export is Mapall/writable).
7. `area51nas1`/`mcp-gate01` are missing from the Tailscale Machines list
   (noticed 2026-11-15, unrelated to anything done in this session — likely
   tied to today's NAS hardware migration needing fresh Tailscale setup on
   the new box). User is handling this themselves (decommissioning both).

### Next up

- `Setup_VictoriaLogs.yaml` playbook to deploy VictoriaLogs to a VM on the
  TrueNAS host — log sink for free-text search, chosen over Loki (no UI
  without Grafana) and Splunk Free (no auth, 500 MB/day, x86 only).
  Single Go binary, local disk only (no object store); data path wants a
  block device (TrueNAS zvol over iSCSI), never an NFS/SMB export. Being
  trialled manually on a VirtualBox VM first; a `logs` inventory group and
  `tvl01` host get added when the playbook is written. BigQuery stays the
  archive; k8s pod logs via a Fluent Bit DaemonSet are a later phase.
- Migrate Photoprism db from local db to MariaDB HA pair
- add more monthly data sets from StatsCan as Airflow DAG's in same way we did
  CPI data
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