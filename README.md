# hive_bot

`hive_bot` is a Discord bot project under milestone-driven development.

Issue `#1` establishes the runtime configuration, logging setup, and application
startup entrypoint. Issue `#2` bootstraps the installable Python package and
quality toolchain around that code. Issue `#3` adds the `/ping` slash command
implementation. Issue `#4` adds guild-scoped slash-command registration
infrastructure. Issue `#5` wires those pieces into a live Discord client.
Issue `#13` adds the Pterodactyl configuration and bridge foundation that later
milestone work will use for discovery-first server management.

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

- live server discovery
- exact server resolution by name or identifier
- current status lookup
- policy budget summaries based on discovered RAM limits

If the panel is unreachable or memory data is incomplete, the bridge returns
structured safe results instead of leaking raw API exceptions.

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

## Manual Validation

1. Create a bot application in the Discord developer portal and install it to
   your target server with the `bot` and `applications.commands` scopes.
2. Put the bot token and target guild ID into `config.local.toml`.
3. Run `python3 -m hive_bot --config config.local.toml`.
4. Verify the bot appears online and logs that it is ready.
5. Verify `/ping` appears in the configured guild and responds with `pong`.
