# hive_bot

`hive_bot` is a Discord bot project under milestone-driven development.

Issue `#1` establishes the runtime configuration, logging setup, and application
startup entrypoint. Discord connectivity and slash commands are implemented in
later milestone issues.

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

Start the application bootstrap with:

```bash
python3 -m hive_bot --config config.local.toml
```

This issue only initializes configuration and logging, then exits successfully.
Discord login and command registration come in later issues.

## Tests

Run the issue checks with:

```bash
pytest --cov=src/hive_bot --cov-report=term-missing --cov-fail-under=100
```

