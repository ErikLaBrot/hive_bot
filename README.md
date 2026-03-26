# hive_bot

`hive_bot` is a Discord bot project under milestone-driven development.

Issue `#1` establishes the runtime configuration, logging setup, and application
startup entrypoint. Issue `#2` bootstraps the installable Python package and
quality toolchain around that code. Discord connectivity and slash commands are
implemented in later milestone issues.

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

The current milestone slice only initializes configuration and logging, then
exits successfully. Discord login and command registration come in later issues.

## Quality Checks

Run the project quality commands with:

```bash
ruff check README.md src tests
mypy src tests
pytest
```
