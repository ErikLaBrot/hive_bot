# hive_bot

`hive_bot` is a Discord bot project under milestone-driven development.

Issue `#1` establishes the runtime configuration, logging setup, and application
startup entrypoint. Issue `#2` bootstraps the installable Python package and
quality toolchain around that code. Issue `#3` adds the `/ping` slash command
implementation in code. Issue `#4` adds guild-scoped slash-command registration
infrastructure. Discord connectivity is completed in a later milestone issue.

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
2. Fill in the Discord bot token and target guild ID.

Example:

```toml
[discord]
token = "replace-me"
guild_id = 123456789012345678

[logging]
level = "INFO"
```

## Run

Start the application bootstrap with either:

```bash
python3 -m hive_bot --config config.local.toml
```

or:

```bash
hive-bot --config config.local.toml
```

The current milestone slice initializes configuration and logging, includes the
`/ping` command implementation, and now includes guild-scoped command
registration infrastructure. Discord client startup still comes in a later
issue, so `/ping` is not yet reachable in a live Discord guild.

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

When the Discord client startup issue lands, the bot will:
- register the milestone commands on its command tree
- sync those commands to the configured target guild

Manual Discord validation of `/ping` remains blocked on the later milestone
issue that adds live Discord connectivity.
