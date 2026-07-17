# glc_v2 — Session 12 reference repository

This is the reference repository for **Part 2** of the Session 12 assignment. It is the glc gateway (the Session 11 `glc_v1` code plus the Modal wrapper `modal_app.py`), left with its security flaws in place on purpose. It is the shared target you open pull requests against when you find a new bug.

## The assignment in one screen

- **Part 1 (required), on your own clone of `glc_v1`.** Migrate it to Modal as Section 6 of the session walks it, then fix every finding in Sections 6 and 7. You submit your hardened repository. This part does not happen here.
- **Part 2 (100 points per new bug), here.** Find a bug that Sections 6 and 7 do not already name, and open a pull request against this repository that describes it, reproduces it from a fresh checkout, and fixes it. The pull-request template walks you through the four things it needs. On duplicates, the first pull request filed wins, so check the open pull requests first.

The full brief is in [`ASSIGNMENT.md`](ASSIGNMENT.md).

## Run it

This is a `uv` project.

```sh
uv sync
uv run glc serve        # gateway on http://localhost:8111
```

To deploy on Modal, see `modal_app.py` and Session 12 Section 6. Use mock keys only, and never put real provider keys on Modal.

## Where to look

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — trust boundaries and data flows. Start here for recon.
- `glc/` — the gateway source.
- `modal_app.py` — the Modal deployment wrapper.
- `/openapi.json` and `/docs` on a running gateway — the full route inventory.

## License

MIT, see [`LICENSE`](LICENSE).
