# Contributing

1. Read `CONSTITUTION.md`. It is one page and it is not negotiable.
2. Find the single home for your concern in `docs/architecture.md` §3 before
   writing a line.
3. New endpoint? Follow the recipe in `docs/architecture.md` §4 and give it an
   evidence level in `docs/api/cloud.md`. Attach the capture (redacted) to the
   pull request if you mark it verified.
4. New non-obvious choice? Add a numbered entry to `docs/decisions.md`. New
   unknown? Add a `Qn` to `docs/open_questions.md`.
5. Tests in the right tier (`docs/testing.md`), fakes from `tests/unit/_fakes.py`,
   no `unittest.mock`, no sleeping for synchronisation.
6. `uv run pre-commit run --all-files` is green: ruff, ruff-format, ty, tests.
7. Commits: imperative subject line, one change per commit, no attribution
   trailers.

## Pull request checklist

- [ ] The change touches only the places the recipe names.
- [ ] No local command path was added (CONSTITUTION §2).
- [ ] Every public method has a docstring that says what the signature does not.
- [ ] No secret can reach a log, a `repr`, or an exception message.
- [ ] Tests assert behaviour, not call plumbing.
- [ ] `docs/` updated where the change alters the map, the API, or the rules.
