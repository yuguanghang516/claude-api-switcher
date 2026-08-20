# Claude API Switcher V4 desktop refresh

## Goal

Ship a polished, open-source Windows desktop utility that can be distributed as a standalone EXE. Preserve the working provider, launcher, gateway, routing, cost, and log features while removing misleading labels and unsafe defaults.

## Product structure

The application uses five clear destinations: Overview, Providers, Smart routing, Activity, and Settings. Provider configuration lives in one place. Overview shows the current Claude Code route, connection health, and recent activity. Models appear under their owning provider instead of in a duplicate top-level management page.

## Visual system

Use one centralized semantic theme module shared by every desktop panel. Support `system`, `light`, and `dark` modes and persist the choice. The direction is a restrained Windows developer tool: neutral surfaces, cobalt primary actions, violet only for AI/model identity, and green/red only for status. Use Microsoft YaHei UI with Segoe UI fallback, consistent 4/8/12/16/24 spacing, 8-12 pixel radii, readable contrast, visible focus, and text labels instead of decorative emoji.

## Functional corrections

- Fix the five-tab language mapping bug.
- Establish one version source and use V4 consistently in the window, build metadata, README, logs, and exports.
- Do not count unconfigured providers or their models as usable.
- Use consistent LongCat Anthropic and OpenAI-compatible endpoints for their respective flows.
- Keep Claude Code launch configuration isolated to the launched process.
- Move gateway credentials to Windows Credential Manager and migrate legacy plaintext values without logging them.
- Bind local services to `127.0.0.1` by default.
- Remove default shared passwords and keep dangerous MCP shell execution disabled unless explicitly configured.
- Make Chinese the complete default UI and keep English translations aligned.

## Quality and release

All existing tests must remain green and new tests must cover theme persistence, tab labels, version consistency, safe credential migration, local-only network defaults, and LongCat endpoint selection. PyInstaller must produce a standalone GUI EXE in `release/`. The built EXE must launch, show the redesigned interface, switch among all three theme modes, and close cleanly without exposing secrets or requiring a Python installation.
