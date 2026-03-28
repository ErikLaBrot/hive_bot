# hive_bot

`hive_bot` is a Discord bot project under milestone-driven development.

Issue `#1` establishes the runtime configuration, logging setup, and application
startup entrypoint. Issue `#2` bootstraps the installable Python package and
quality toolchain around that code. Issue `#3` adds the `/ping` slash command
implementation. Issue `#4` adds guild-scoped slash-command registration
infrastructure. Issue `#5` wires those pieces into a live Discord client.
Issue `#13` adds the Pterodactyl configuration and bridge foundation that later
milestone work will use for discovery-first server management. Issue `#11`
adds the first `/server` read-only Discord commands on top of that bridge.
Issue `#12` adds the controlled `/server` power actions with policy enforcement
and audit logging.

## Setup

Create a virtual environment, activate it, and install the project with
development dependencies:

```bash
python3 -m pip install -r requirements.txt
```

This installs the package in editable mode along with the linting, typing, and
test tools used in this repository.

## Configuration

1. Copy `config.example.toml` to `config.local.toml`.
2. Fill in the Discord bot token, target guild ID, Pterodactyl panel URL, API
   key, and policy limits.

Example:

```toml
[discord]
token = "replace-me"
guild_id = 123456789012345678

[pterodactyl]
panel_url = "https://panel.example.com"
api_key = "replace-me"

[policy]
max_running_servers = 2
max_total_ram_gb = 10

[logging]
level = "INFO"
```

The Pterodactyl sections are discovery and policy only. The bot does not keep a
static local registry of server names or IDs for this milestone.

## Run

Start the bot with either:

```bash
python3 -m hive_bot --config config.local.toml
```

or:

```bash
hive-bot --config config.local.toml
```

Running the CLI now loads config, configures logging, starts the Discord
client, registers the milestone commands, and syncs them to the configured
guild during startup.

## Pterodactyl Foundation

Issue `#13` introduces a shared bridge in `src/hive_bot/pterodactyl/` that uses
`py-dactyl` and fresh panel discovery as the source of truth. The bridge now
supports:

- live server discovery with request-scoped state enrichment
- exact server resolution by name or identifier
- current status lookup
- policy budget summaries based on discovered RAM limits
- controlled start, stop, and restart requests for discoverable servers

If the panel is unreachable or memory data is incomplete, the bridge returns
structured safe results instead of leaking raw API exceptions.

## `/server` Commands

Issues `#11` and `#12` add the discovery-driven `/server` command group:

- `/server list`
- `/server status <server>`
- `/server start <server>`
- `/server stop <server>`
- `/server restart <server>`
- `/server budget`
- `/server help`

These commands always discover the accessible Pterodactyl server inventory at
invocation time, then format safe Discord responses for success, not-found,
ambiguous-match, partial-budget, policy denial, no-op, and panel-unreachable
results.

`/server list` now keeps the output intentionally small:

- one line per discoverable server
- server name
- live current status when it can be confirmed
- `unknown` for an individual server if that server's live state lookup fails

The power commands are intentionally conservative:

- `/server start` denies the request if the bot would exceed
  `max_running_servers`, exceed `max_total_ram_gb`, or cannot compute RAM
  safety confidently because the target or currently running discovered servers
  have unknown RAM limits.
- `/server stop` only acts on servers that live state enrichment shows as
  running.
- `/server restart` only acts on servers that live state enrichment shows as
  running and
  never behaves like an implicit start.
- every `/server start`, `/server stop`, and `/server restart` attempt emits an
  audit log entry with the Discord user, query, resolved server, outcome, and
  denial reason when applicable.
- accepted `/server start`, `/server stop`, and `/server restart` commands send
  an immediate accepted response first, then a follow-up message after
  websocket-plus-poll monitoring confirms success or gives up and tells a human
  to check the panel manually.

## Quality Checks

Run the project quality commands with:

```bash
ruff check README.md src tests
mypy src tests
pytest
```

## `/ping` Command

The `/ping` slash command is implemented in `src/hive_bot/commands/ping.py` and
responds with exactly `pong`.

## Command Registration

Guild-scoped registration infrastructure is implemented in
`src/hive_bot/command_registry.py`.

When the bot connects successfully, it will:
- register the milestone commands on its command tree
- sync those commands to the configured target guild
- log the connected bot identity for manual ready-state verification
- expose `/ping` and the `/server` command group in the configured guild

## Manual Validation

1. Create a bot application in the Discord developer portal and install it to
   your target server with the `bot` and `applications.commands` scopes.
2. Put the bot token and target guild ID into `config.local.toml`.
3. Run `python3 -m hive_bot --config config.local.toml`.
4. Verify the bot appears online and logs that it is ready.
5. Verify `/ping` appears in the configured guild and responds with `pong`.
6. Verify `/server help` appears and lists all supported commands.
7. Verify `/server list`, `/server status <server>`, and `/server budget`
   return live Pterodactyl-backed responses for the configured bot user.
8. Verify `/server start <server>`, `/server stop <server>`, and
   `/server restart <server>` return clean accepted, denied, or no-op
   responses based on live discovery and policy limits, then send a follow-up
   completion message for accepted actions.
9. Verify the bot logs an audit entry for each `/server start`, `/server stop`,
   and `/server restart` attempt, plus a second monitor audit entry for each
   accepted action follow-up.
