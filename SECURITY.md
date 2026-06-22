# Security Policy

## Reporting a vulnerability

Please report security issues **privately** through GitHub's private vulnerability
reporting:

> Repository **Security** tab → **Report a vulnerability**

This opens a private advisory channel with the maintainer. Please do **not** open
a public issue for security problems.

Include in your report:

- a description of the issue and its impact,
- steps to reproduce (a minimal config or command if relevant),
- the affected version / commit.

You'll get an acknowledgement, and a fix or mitigation will be coordinated before
any public disclosure. Please allow a reasonable window to address the issue
before disclosing it publicly.

_(Private vulnerability reporting must be enabled in repository Settings → Code
security before it's available — see the pre-public checklist.)_

## Scope

led-ticker runs on a Raspberry Pi on a local network and is configured through a
trusted TOML file. The most relevant areas are the optional network-facing
surfaces: the web-status sidecar (`[web]`) and the busy-light HTTP listener
(`[busy_light]` with `source = "http"`). Secrets (API keys, tokens) belong in
`.env` / environment variables, never in `config.toml` — see the configuration
docs at <https://docs.ledticker.dev>.
