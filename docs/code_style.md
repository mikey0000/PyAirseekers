# Code style

Ruff and ty enforce most of this (`pyproject.toml`); the rest is convention
and gets caught in review. Where this document and a linter disagree, fix the
linter configuration, not the code.

## Language and tooling

- Python 3.13 or newer: `type X = ...` aliases, PEP 695 generics, `match`,
  `Self`.
- `uv` manages the environment. `uv run ruff check --fix .`,
  `uv run ruff format .`, `uv run ty check`, `uv run pytest`.
- Line length 120. Ruff `select = ["ALL"]` with a short ignore list; every
  ignore has a comment saying why.
- Runtime dependency: `aiohttp` only. Extras for experimental transports.

## Structure

- **One concern per module.** A module docstring says what it owns in one
  sentence.
- **Top-level imports only.** Type-only names go in a `TYPE_CHECKING` block.
- **Layers import as `architecture.md` §1 draws them.** `cloud`, `local` and
  `live` never import each other.
- **Protocols for seams a test replaces** (`Requester`). Inheritance is for
  shared implementation only.
- **Public names are curated** through `__all__`.

## Typing

- Everything is annotated, including tests. `ty` runs clean on the package.
- No `Any` in a public signature. Raw JSON is `Json` / `JsonObject`
  (`cloud/transport.py`, `cloud/api.py`); decoded ROS1 messages are `object`.
- `X | None`, `list[X]`, `Mapping` for read-only parameters.
- Narrow raw JSON with `isinstance`, never with a cast.

## Async

- Every I/O method is `async def`. Nothing blocks the loop.
- `asyncio.Lock` guards state that spans an `await`; re-check after acquiring.
- Every external wait is bounded by a timeout from `const.py`.
- A task the library starts is owned and cancelled by the object that started
  it (`FoxgloveClient._receive_task`).

## Naming

- Methods are named for what the caller wants (`dock`, `get_full_status`,
  `open_live_stream`), not for the HTTP verb. The path lives in `const.py`.
- Wire names (`task_units`, `truning_mode`, `SetDarkMode`) appear only in
  bodies and `const.py`; Python names are `snake_case`.
- Exceptions start with `Airseekers` and end in `Error`.
- Booleans read as predicates: `connected`, `is_authorized`.

## Errors

- Raise only the classes in `exceptions.py`. A failed command raises; it never
  returns `False`.
- Messages describe the condition, never include a secret, a token, a
  live-stream URL or a full response body. Structured fields (`code`, `path`)
  are attributes.
- Catch the narrowest exception that can occur. A broad `except Exception` is
  allowed only in the Foxglove receive loop and schema registration, where a
  bad frame must not kill the stream, and it logs with `exc_info`.

## Logging

- One module logger: `_LOGGER = logging.getLogger(__name__)`.
- DEBUG for request outlines (method, path, status), INFO for login (token
  fingerprint only), WARNING for a rejected refresh or a bridge warning.
- `%s` formatting in log calls, never f-strings.

## Comments and docstrings

- Default to no comment. Write one for a server quirk, an evidence gap, a
  workaround: one or two lines, citing `Dn` or `Qn` when it applies.
- Every public module, class and method has a docstring: a summary line, then
  only what the signature does not say. Google style sections when there is
  more than one thing to say.
- No section-divider comments, no commented-out code, no `TODO` without a
  backlog entry.
