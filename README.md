# Kestra MCP

MCP server for [Kestra](https://kestra.io), generated from Kestra's own OpenAPI spec via
[FastMCP](https://gofastmcp.com) rather than hand-written per endpoint.

`scripts/fetch_spec.py` downloads the OpenAPI 3 spec Kestra publishes in
[kestra-io/client-sdk](https://github.com/kestra-io/client-sdk) (the same one its official SDKs
are built from) and ships it as package data. `FastMCP.from_openapi()` turns it into MCP tools.
Re-running the script picks up upstream API changes without touching any code.

There is no hand-maintained operation list. Everything that decides what is served comes from
the spec:

| Concern | Taken from |
| --- | --- |
| Toolsets | The operation's OpenAPI tag (`Flows` → `flows`, `Blueprint Tags` → `blueprint-tags`) |
| Read vs. write | HTTP method. `GET` is read (except the `triggerExecutionByGetWebhook*` webhook triggers, which start a run), plus POSTs named `get*`/`list*`/`search*`/`validate*`/`export*`/`preview*` (e.g. `validateFlows`, `exportFlowsByIds`) |
| OSS vs. Enterprise | Kestra's `x-kestra: {edition: ee}` operation extension |

The only spec adjustments happen at load time in [`server.py`](src/kestra_mcp/server.py):
`{tenant}` is baked into every path from `KESTRA_TENANT` so tools don't each ask for it, and the
one request body upstream declares without a content type (`updateFlowsInNamespace`) gets the YAML
string type its sibling flow endpoints use.

## Configuration

| Env var | Default | Effect |
| --- | --- | --- |
| `KESTRA_URL` | (required) | Base URL of the instance, e.g. `http://localhost:8080` |
| `KESTRA_API_TOKEN` | | Sent as `Authorization: Bearer …` (Enterprise/Cloud API tokens) |
| `KESTRA_USERNAME` / `KESTRA_PASSWORD` | | Basic auth (OSS). Ignored if a token is set. Neither set: no auth |
| `KESTRA_TENANT` | `main` | Tenant for all tenant-scoped endpoints. OSS is always `main` |
| `KESTRA_EDITION` | `oss` | `oss` drops Enterprise-only endpoints, `ee` serves everything |
| `KESTRA_TOOLSETS` | `all` | Comma-separated toolsets, e.g. `flows,executions,logs,kv` |
| `KESTRA_READ_ONLY` | `false` | `true` drops every write tool |

Filtered tools are never registered, so they can't be called by name either. Each tool carries
the MCP `readOnlyHint` (and `destructiveHint` for `DELETE`) annotations, plus tags for its toolset
and `read`/`write`.

With the current spec that is **209 tools for OSS** (106 read-only) and **611 for Enterprise**
(280 read-only). That is a lot of tools for a client to carry, so narrowing with
`KESTRA_TOOLSETS` is worth it, e.g. `flows,executions,logs,kv,namespaces,triggers`.

OSS toolsets: `ai`, `blueprint-tags`, `blueprints`, `dashboards`, `executions`, `expressions`,
`files`, `flows`, `kv`, `logs`, `mcp`, `metrics`, `misc`, `namespaces`, `outputs`, `plugins`,
`secrets`, `triggers`. Enterprise adds users, groups, roles, tenants, apps, policies, audit logs,
and more. An unknown name in `KESTRA_TOOLSETS` fails at startup and lists the valid ones.

`uv run python scripts/list_tools.py` prints exactly which tools a given combination of these env
vars leaves enabled, with their tags and per-toolset counts.

## Setup

```bash
uv sync
cp .env.example .env   # fill in KESTRA_URL and credentials
uv run kestra-mcp
```

## Updating the spec

```bash
uv run python scripts/fetch_spec.py --check   # is there an upstream update? writes nothing, exit 1 if so
uv run python scripts/fetch_spec.py           # pull it into the package
uv run python scripts/fetch_spec.py --url http://localhost:8080/swagger/kestra.yml   # or your own instance's spec
```

The script reports which operations upstream added, removed, or moved. Then reinstall with
`uv tool install --reinstall .`.

## Installing it as a standalone command

The spec ships as package data (`src/kestra_mcp/openapi/`), so the installed command doesn't
depend on this checkout:

```bash
uv tool install .          # from a checkout, or:
uv tool install git+https://github.com/WildDogOne/KestraMCP
```

## Wiring into Claude Code

This runs over **stdio**. MCP server subprocesses don't inherit Claude Code's environment, so pass
the `KESTRA_*` variables explicitly. Positional arguments (`<name>` then `<command>`) must come
before any `-e` flags:

```bash
claude mcp add --scope user kestra kestra-mcp \
  -e KESTRA_URL=http://localhost:8080 \
  -e KESTRA_USERNAME=<user> \
  -e KESTRA_PASSWORD=<password> \
  -e KESTRA_TOOLSETS=flows,executions,logs,kv,namespaces,triggers
```

To keep secrets out of shell history, export them in your shell instead and reference them from
`.mcp.json` as `"env": {"KESTRA_PASSWORD": "${KESTRA_PASSWORD}", ...}`.
