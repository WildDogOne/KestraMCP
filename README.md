# Kestra MCP

An MCP server that lets Claude (or any MCP client) manage a [Kestra](https://kestra.io) instance:
search and edit flows, run and debug executions, read logs, manage key-value pairs and triggers.

All tools are **generated from Kestra's own OpenAPI spec** with
[FastMCP](https://gofastmcp.com), not hand-written per endpoint. When Kestra's API changes,
re-running one script picks up the change without touching any code.

- **Generated, not maintained:** every endpoint in the spec becomes a tool. There's no operation list to keep in sync.
- **Filterable:** limit the tools to the parts of the API you need, to read-only, or to the OSS edition.
- **Safe by default for clients:** each tool is marked read or write (MCP `readOnlyHint`/`destructiveHint`), so clients can allow reads and prompt for writes.

## Requirements

- Python ≥ 3.11 and [uv](https://docs.astral.sh/uv/)
- A Kestra instance reachable over HTTP(S), with basic auth (OSS) or an API token (Enterprise/Cloud)

## Quick start

```bash
git clone https://github.com/WildDogOne/KestraMCP && cd KestraMCP
uv tool install .            # puts `kestra-mcp` on your PATH
claude mcp add --scope user kestra kestra-mcp \
  -e KESTRA_URL=https://kestra.example.com \
  -e KESTRA_USERNAME=<user> \
  -e KESTRA_PASSWORD=<password> \
  -e KESTRA_TOOLSETS=flows,executions,logs,kv,namespaces,triggers
```

Then run `/mcp` in Claude Code and check that `kestra` shows as connected. Ask something like
"list my Kestra namespaces" to confirm it works.

The spec ships inside the package, so the installed command doesn't need this checkout afterwards.

Notes on `claude mcp add`:
- `kestra kestra-mcp` (name, then command) must come **before** the `-e` flags, or the command won't parse.
- The server runs over stdio and does **not** inherit Claude Code's environment, so every `KESTRA_*` variable has to be passed with `-e`.
- To keep the password out of shell history, export it in your shell and reference it from `.mcp.json` as `"env": {"KESTRA_PASSWORD": "${KESTRA_PASSWORD}"}`.

## Configuration

| Env var | Default | Effect |
| --- | --- | --- |
| `KESTRA_URL` | (required) | Base URL of the instance, without `/api/v1`, e.g. `http://localhost:8080` |
| `KESTRA_API_TOKEN` | | Sent as `Authorization: Bearer …` (Enterprise/Cloud API tokens) |
| `KESTRA_USERNAME` / `KESTRA_PASSWORD` | | Basic auth (OSS). Ignored if a token is set. Neither set: no auth |
| `KESTRA_TENANT` | `main` | Tenant for tenant-scoped endpoints. OSS is always `main` |
| `KESTRA_EDITION` | `oss` | `oss` drops Enterprise-only endpoints, `ee` serves everything |
| `KESTRA_TOOLSETS` | `all` | Comma-separated toolsets, e.g. `flows,executions,logs,kv` |
| `KESTRA_READ_ONLY` | `false` | `true` drops every write tool |

When running from a checkout, a `.env` file in the current directory is also read (see
[`.env.example`](.env.example)).

### Choosing toolsets

With the current spec the server exposes **209 tools for OSS** (106 read-only) and **611 for
Enterprise** (280 read-only). That's a lot for a client to carry, so narrow it with
`KESTRA_TOOLSETS`. `flows,executions,logs,kv,namespaces,triggers` covers day-to-day work with
138 tools.

OSS toolsets: `ai`, `blueprint-tags`, `blueprints`, `dashboards`, `executions`, `expressions`,
`files`, `flows`, `kv`, `logs`, `mcp`, `metrics`, `misc`, `namespaces`, `outputs`, `plugins`,
`secrets`, `triggers`. Enterprise adds users, groups, roles, tenants, apps, policies, audit logs,
and more. An unknown name fails at startup and lists the valid ones.

To see exactly which tools a combination enables (no Kestra connection needed):

```bash
KESTRA_URL=x KESTRA_TOOLSETS=flows,kv uv run python scripts/list_tools.py
```

```text
listFlowsByNamespace [flows, read]
createFlow [flows, write]
...
Total tools: 44
  flows: 38
  kv: 6
```

Filtered tools are never registered, so they can't be called by name either.

## Client permission rules

Read-only mode is the simplest guard. For finer control, auto-allow the read tools and prompt for
the write tools in `~/.claude/settings.json`. These commands print the rule names for your
toolset selection:

```bash
export KESTRA_URL=x KESTRA_TOOLSETS=flows,executions,logs,kv,namespaces,triggers
uv run python scripts/list_tools.py | grep -E '\[.*\bread\b'  | cut -d' ' -f1 | sed 's/^/mcp__kestra__/'   # → permissions.allow
uv run python scripts/list_tools.py | grep -E '\[.*\bwrite\b' | cut -d' ' -f1 | sed 's/^/mcp__kestra__/'   # → permissions.ask
```

Tools that touch secrets deserve separate treatment. Kestra's API never returns secret values
from its secret endpoints, but it can evaluate expressions:

| Tool | Returns | Suggested rule |
| --- | --- | --- |
| `getInheritedSecrets`, `listSecrets` | Secret **names** only, per namespace. Useful for writing `{{ secret('…') }}` in flows | allow |
| `evalExpression`, `evalTaskRunExpression` | The result of any Pebble expression against a real execution. Useful for debugging templating, but `{{ secret('X') }}` returns the **decrypted value** | ask, and reject expressions containing `secret(` |

## How it works

[`scripts/fetch_spec.py`](scripts/fetch_spec.py) downloads the OpenAPI 3 spec Kestra publishes in
[kestra-io/client-sdk](https://github.com/kestra-io/client-sdk), the same spec its official SDKs
are built from. It covers both editions and ships as package data. At startup,
`FastMCP.from_openapi()` turns it into tools, and everything that decides what is served comes
from the spec itself:

| Concern | Taken from |
| --- | --- |
| Toolsets | The operation's OpenAPI tag (`Flows` → `flows`, `Blueprint Tags` → `blueprint-tags`) |
| Read vs. write | HTTP method: `GET` is read, except the `triggerExecutionByGetWebhook*` tools, which start a run. POSTs named `get*`/`list*`/`search*`/`validate*`/`export*`/`preview*` (e.g. `validateFlows`) are read too |
| OSS vs. Enterprise | Kestra's `x-kestra: {edition: ee}` operation extension |

The only adjustments happen at load time in [`server.py`](src/kestra_mcp/server.py):
- **Tenant:** `{tenant}` is filled into every path from `KESTRA_TENANT`, so tools don't each ask for it.
- **One spec bug:** `updateFlowsInNamespace` has a request body without a content type. It gets the YAML string type that its sibling flow endpoints use.

## Updating the spec

```bash
uv run python scripts/fetch_spec.py --check   # upstream changed? writes nothing, exits 1 if so
uv run python scripts/fetch_spec.py           # pull it into the package
uv run python scripts/fetch_spec.py --url http://localhost:8080/swagger/kestra.yml   # or your instance's own spec
uv tool install --reinstall .                 # then reinstall the command
```

The script reports which operations upstream added, removed or moved.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `CERTIFICATE_VERIFY_FAILED … unable to get local issuer certificate` | The server sends its certificate without the intermediate. Browsers fill that in themselves; Python doesn't. Configure the full chain on the reverse proxy (Apache: `SSLCertificateChainFile`). Check with `openssl s_client -connect <host>:443 -servername <host>`, which should report `Verify return code: 0` |
| `HTTP 302` to a login page | An SSO layer (e.g. Shibboleth) in front of Kestra also covers `/api/`. Exempt `/api/` from SSO and let Kestra's own auth protect it |
| `HTTP 401 … Authentication required` from Kestra | Wrong credentials, or they changed after `claude mcp add`. Re-add the server, then restart it with `/mcp`. Recent OSS versions require basic auth |
| List results arrive as `{"result": [...]}` | Expected. MCP structured output must be an object, so FastMCP wraps array responses |

## Limitations

- Tested end-to-end against Kestra OSS. Enterprise endpoints are generated from the same spec but haven't been exercised against a live Enterprise instance.
- Response schemas aren't validated. Kestra's declared schemas don't always match what it returns.
- No browser/SSO login. The server authenticates with basic auth or an API token only.
