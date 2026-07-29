# PER-321: Self-Hosting Hardening, Privacy & Dogfooding — Implementation Plan

For agentic workers: Execute the numbered tasks in order. Each task is TDD:
write the test first, run it and confirm it FAILS for the stated reason, write the
minimal real implementation, run it and confirm it PASSES, then commit with the
exact conventional message given. Steps are sized at 2–5 minutes. There are NO
placeholders — every step ships real code or a real script. All types referenced by a
task are defined in that task or an earlier one. Run backend tests with
`cd /home/kitts/Documents/dev/personal/archivum && uv run pytest <path> -q` (pytest.ini
sets `pythonpath = apps/backend`). Run script/ops tests the same way (they invoke the
script via `subprocess`). Absolute repo root: `/home/kitts/Documents/dev/personal/archivum`.

## Goal

Turn Archivum into a durable, private, single-owner personal knowledge system:
reliable deploy; backup that captures only precious data (L0 evidence + L1 SQLite) and
restore that rebuilds derived indexes (L2); at-rest encryption + disciplined secret
handling; scope-based access control enforced at query time; structured observability
across ingest + retrieval; a versioned schema migration runner; failure recovery for
interrupted ingest and partial index rebuild; and a dogfooding harness with a
retrieval-quality eval over a real fixture corpus (docs + conversations + a repo) that
measures cited-answer correctness, "insufficient evidence" behavior, and context-package
token size.

## Architecture

Layered model from the architecture spec (§2). Precious layers are backed up; derived
layers are rebuilt:

```
L3  Generated Views      (regenerable projections)
L2  Derived Indexes      Qdrant · Kuzu · SQLite FTS   ← REBUILDABLE (rebuild on restore)
L1  Canonical Knowledge  SQLite (/data/archivum.db)   ← PRECIOUS (backed up)
L0  Immutable Evidence   content-addressed blob store ← PRECIOUS (backed up)
```

Backup dumps L0 + L1 into a single versioned, integrity-checked archive. Restore unpacks
L0 + L1, then invokes `rebuild_indexes()` to regenerate L2 from L1 (spec §6.6: any L2/L3
can be deleted and regenerated from L1 without data loss). Scope (spec §4) is a partition
+ access label carried on every knowledge object and enforced by a query-time filter.
Everything evolves the existing FastAPI + SQLite + Qdrant + Kuzu + Caddy + MCP stack.

New Python modules live under `apps/backend/archivum/`:
`blob_store.py` (L0), `backup.py` (dump/restore orchestration), `crypto.py` (at-rest
encryption), `scope.py` (scope model + query-time enforcement), `migrations/` (runner +
versioned migrations), `metrics.py` (in-process counters/histograms), and
`api/health.py` (health/metrics endpoints). The dogfooding harness lives under
`apps/backend/archivum/dogfood/` with fixtures in `tests/dogfood/fixtures/`. A
`scripts/backup.sh` + `scripts/restore.sh` wrap the Python entrypoints for ops.

## Tech Stack

- Python 3.12, FastAPI, aiosqlite, pydantic-settings (existing).
- `cryptography` (Fernet / AES-GCM) for at-rest encryption — add to
  `apps/backend/pyproject.toml`.
- Qdrant + Kuzu clients (existing) for L2 rebuild.
- pytest + pytest-asyncio (`asyncio_mode = auto` in pytest.ini) for all tests.
- Bash + `subprocess`-driven pytest for ops scripts (`scripts/backup.sh`, `restore.sh`).
- Docker Compose + Caddy for deployment surface (existing patterns).

## Global Constraints

From the architecture spec — these are invariants for every task:

1. **Back up L0 + L1 only.** Backups contain the content-addressed blob store (L0) and
   the SQLite store of record (L1). They MUST NOT contain Qdrant, Kuzu, or FTS data.
2. **Rebuild L2 on restore.** Restore reconstructs derived indexes by calling
   `rebuild_indexes()` from L1; it never restores L2 from an archive.
3. **Scope enforced at query time.** Every retrieval path filters by the caller's allowed
   scopes. Cross-scope reads MUST be impossible via any query surface (API + MCP).
4. **Single-owner, self-hosted.** No multi-tenant assumptions. The owner holds all
   scopes; access control partitions the owner's own data, not other users.
5. **Evolve in place.** Keep FastAPI + SQLite + Qdrant + Kuzu + Caddy + MCP. Add modules;
   do not rewrite. Reshape schema via the migration runner, never by ad-hoc edits.
6. **Evidence is immutable (L0).** Blobs are content-addressed (sha256), written once,
   never mutated. Encryption wraps blobs at rest without changing their content address.

## File Structure

```
apps/backend/archivum/
  blob_store.py                 # L0 content-addressed blob store
  crypto.py                     # at-rest encryption (Fernet), key derivation
  backup.py                     # dump_backup() / restore_backup()
  scope.py                      # Scope model + enforce_scope() query filter
  metrics.py                    # in-process counters + histograms
  observability.py              # (existing) trace ids + spans — extended
  api/health.py                 # /api/health, /api/health/ready, /api/metrics
  migrations/
    __init__.py                 # migration registry + Migration type
    runner.py                   # apply_migrations(), current_version()
    m0001_scope_columns.py      # add scope column to knowledge tables
    m0002_ingest_checkpoints.py # ingest checkpoint table for resume
  ingest/
    checkpoint.py               # resumable ingest checkpoints (failure recovery)
  dogfood/
    __init__.py
    harness.py                  # ingest fixture corpus, run question set
    eval.py                     # score cited answers + insufficient-evidence + tokens
scripts/
  backup.sh                     # ops wrapper → python -m archivum.backup dump
  restore.sh                    # ops wrapper → python -m archivum.backup restore
tests/
  backup/test_blob_store.py
  backup/test_backup_roundtrip.py
  backup/test_backup_excludes_l2.py
  backup/test_backup_scripts.py
  crypto/test_crypto.py
  crypto/test_config_secrets.py
  scope/test_scope_model.py
  scope/test_scope_enforcement.py
  scope/test_scope_api_isolation.py
  observability/test_metrics.py
  observability/test_health.py
  migrations/test_runner.py
  migrations/test_forward_migration.py
  ingest/test_checkpoint_resume.py
  ingest/test_partial_rebuild.py
  dogfood/fixtures/            # docs + conversations + a small repo
  dogfood/test_harness.py
  dogfood/test_retrieval_eval.py
docs/ops/backup-restore.md      # operator runbook
```

## Upstream Dependencies

- **Architecture spec** `docs/superpowers/specs/2026-07-28-archivum-architecture-design.md`
  — CANONICAL. §2 layer/volume mapping, §4 scope, §6 trust invariants, §9 migration.
- **PER-319 (cited retrieval, Ask, MCP)** — plan file
  `docs/superpowers/plans/2026-07-28-per319-cited-retrieval-ask-and-mcp.md` is **absent**
  at write time. ASSUMPTION: retrieval exposes a context-package builder and an
  "insufficient evidence" answer path per spec §6.5 and §8. This plan defines a thin
  `retrieval` shim interface (Task 8) so scope enforcement + the eval can proceed; when
  PER-319 lands, re-point the shim at the real retriever (single import swap).
- **PER-320 (standalone product experience)** — plan file
  `docs/superpowers/plans/2026-07-28-per320-standalone-product-experience.md` is **absent**
  at write time. ASSUMPTION: the CLI (`packages/archivum-cli`) and Compose stack are the
  deployment surface; backup/restore ops scripts integrate there without depending on
  unshipped UX.
- **Existing code** this plan builds on: `db/sqlite.py` (`init_db`, `get_db`,
  `list_pages`), `api/system.py::rebuild_indexes`, `config.py::Settings`,
  `observability.py` (`span`, trace ids), `auth.py` (`CurrentUser`, `require_owner`),
  `rate_limit.py` (middleware pattern), `ingest/pipeline.py::ingest`.

---

### Task 1 — L0 content-addressed blob store

**Files:** `apps/backend/archivum/blob_store.py`, `tests/backup/test_blob_store.py`

**Interfaces:**
- Produces:
  - `class BlobRef(BaseModel): sha256: str; size: int; path: Path`
  - `class BlobStore:` with
    - `__init__(self, root: Path) -> None`
    - `put(self, data: bytes) -> BlobRef` — content-address (sha256), write once under
      `root/<sha[:2]>/<sha>`, idempotent (re-put of same bytes returns same ref, no
      rewrite).
    - `get(self, sha256: str) -> bytes` — raises `KeyError` if absent.
    - `exists(self, sha256: str) -> bool`
    - `iter_refs(self) -> Iterator[BlobRef]` — enumerate all stored blobs.
- Consumes: `pathlib.Path`, `hashlib`.

Steps:
- [ ] Create `tests/backup/__init__.py` (empty) and `tests/backup/test_blob_store.py`
      with `test_put_is_content_addressed`: `put(b"hello")` returns a `BlobRef` whose
      `sha256 == hashlib.sha256(b"hello").hexdigest()` and `size == 5`.
- [ ] Run `uv run pytest tests/backup/test_blob_store.py -q` → FAIL (module missing).
- [ ] Implement `BlobRef` and `BlobStore.put/get/exists` in `blob_store.py` with the
      sharded path layout and `mkdir(parents=True, exist_ok=True)`.
- [ ] Run the test → PASS.
- [ ] Add `test_put_is_idempotent`: putting the same bytes twice does not change mtime and
      `get()` round-trips the bytes; add `test_get_missing_raises` (`KeyError`). Run → PASS.
- [ ] Add `iter_refs` + `test_iter_refs_lists_all` (put 3 distinct blobs, assert 3 refs
      with matching hashes). Run → PASS.
- [ ] Commit: `feat(blob-store): add L0 content-addressed blob store`

### Task 2 — At-rest encryption for L0/L1

**Files:** `apps/backend/archivum/crypto.py`, `tests/crypto/test_crypto.py`,
`apps/backend/pyproject.toml`

**Interfaces:**
- Produces:
  - `def derive_key(passphrase: str, salt: bytes) -> bytes` — PBKDF2-HMAC-SHA256,
    200_000 iters, returns 32-byte urlsafe-base64 Fernet key.
  - `class Encryptor:` `__init__(self, key: bytes)`; `encrypt(self, data: bytes) -> bytes`;
    `decrypt(self, token: bytes) -> bytes` (raises `InvalidToken` on tamper/wrong key).
  - `def encrypt_file(src: Path, dst: Path, enc: Encryptor) -> None`
  - `def decrypt_file(src: Path, dst: Path, enc: Encryptor) -> None`
- Consumes: `cryptography.fernet.Fernet`, `cryptography.hazmat...PBKDF2HMAC`.

Steps:
- [ ] Add `cryptography>=42` to `[project.dependencies]` in `apps/backend/pyproject.toml`.
- [ ] Create `tests/crypto/__init__.py` and `tests/crypto/test_crypto.py` with
      `test_roundtrip`: `enc.decrypt(enc.encrypt(b"secret")) == b"secret"`.
- [ ] Run `uv run pytest tests/crypto/test_crypto.py -q` → FAIL (module missing).
- [ ] Implement `derive_key`, `Encryptor` in `crypto.py`. Run → PASS.
- [ ] Add `test_wrong_key_raises` (decrypt with a different derived key raises
      `cryptography.fernet.InvalidToken`) and `test_derive_key_deterministic` (same
      passphrase+salt → same key; different salt → different key). Run → PASS.
- [ ] Implement `encrypt_file`/`decrypt_file`; add `test_file_roundtrip` over a temp file
      of 10 KB random bytes. Run → PASS.
- [ ] Commit: `feat(crypto): add at-rest encryption for L0/L1`

### Task 3 — Secret handling in config

**Files:** `apps/backend/archivum/config.py`, `.env.example`,
`tests/crypto/test_config_secrets.py`

**Interfaces:**
- Produces (on `Settings`):
  - `backup_encryption_enabled: bool = False`
  - `backup_passphrase: str = ""` (secret; read from env `BACKUP_PASSPHRASE`)
  - `backup_dir: Path = Path("/data/backups")`
  - `def redacted_secrets(self) -> dict[str, str]` — returns config with secret fields
    masked as `"***"` (jwt_secret, anthropic_api_key, mcp_api_key, backup_passphrase,
    openrouter_api_key, openai_compat_api_key, embed_api_key).
  - `def require_encryption_ready(self) -> None` — raises `ValueError` if
    `backup_encryption_enabled` but `backup_passphrase` is empty.

Steps:
- [ ] Write `tests/crypto/test_config_secrets.py::test_redacted_secrets_masks_secrets`:
      construct `Settings(jwt_secret="abc", backup_passphrase="pw")`, assert
      `redacted_secrets()["jwt_secret"] == "***"` and no raw secret value appears in the
      dict's `str()`.
- [ ] Run → FAIL (method missing).
- [ ] Add the four fields + `redacted_secrets` + `require_encryption_ready` to `Settings`.
      Run → PASS.
- [ ] Add `test_require_encryption_ready_raises_without_passphrase` (enabled + empty
      passphrase → `ValueError`; enabled + set passphrase → no raise). Run → PASS.
- [ ] Append `BACKUP_ENCRYPTION_ENABLED`, `BACKUP_PASSPHRASE` (with
      `# generate with: openssl rand -hex 32`), and `BACKUP_DIR` to `.env.example` under a
      new `# ─── Backups ───` section.
- [ ] Commit: `feat(config): add backup + secret redaction settings`

### Task 4 — Backup dump (L0 + L1 only)

**Files:** `apps/backend/archivum/backup.py`, `tests/backup/test_backup_excludes_l2.py`

**Interfaces:**
- Produces:
  - `class BackupManifest(BaseModel): version: int; created_at: str; schema_version: int;
     db_sha256: str; blob_count: int; encrypted: bool`
  - `async def dump_backup(settings: Settings, out_path: Path, enc: Encryptor | None) ->
     BackupManifest` — writes a `.tar.gz` (or `.tar.gz.enc`) containing exactly:
     `manifest.json`, `l1/archivum.db` (a `VACUUM INTO` consistent copy), and
     `l0/<sharded blobs>`. Excludes Qdrant/Kuzu/FTS entirely.
- Consumes: `blob_store.BlobStore`, `crypto.Encryptor`, `db.sqlite` (db path),
  `migrations.runner.current_version` (for `schema_version`).

Steps:
- [ ] Write `test_backup_excludes_l2`: build a temp settings pointing db_path + blob root
      + fake `kuzu_path`/qdrant markers at temp dirs, seed one page row + one blob, call
      `dump_backup(...)`, untar to a temp dir, assert members are only under
      `{manifest.json, l1/, l0/}` and NO member path contains `kuzu`, `qdrant`, or `fts`.
- [ ] Run → FAIL (module missing).
- [ ] Implement `BackupManifest` + `dump_backup`: use SQLite `VACUUM INTO` for a
      consistent L1 copy, walk `BlobStore.iter_refs()` for L0, write `manifest.json`, tar
      with gzip; if `enc` provided, encrypt the tarball via `crypto.encrypt_file`. Run → PASS.
- [ ] Add `test_manifest_records_counts` (manifest `blob_count` matches seeded blobs;
      `db_sha256` matches the tarred db file). Run → PASS.
- [ ] Add `python -m archivum.backup dump` CLI entry in `backup.py` `__main__` block
      (argparse: `--out`, reads settings). Run existing tests → PASS.
- [ ] Commit: `feat(backup): dump L0+L1 archive excluding derived indexes`

### Task 5 — Restore + rebuild L2

**Files:** `apps/backend/archivum/backup.py`, `apps/backend/archivum/api/system.py`
(reuse `rebuild_indexes` logic), `tests/backup/test_backup_roundtrip.py`

**Interfaces:**
- Produces:
  - `async def restore_backup(settings: Settings, archive: Path, enc: Encryptor | None,
     rebuild: Callable[[Settings], Awaitable[dict]]) -> BackupManifest` — decrypts if
     needed, verifies `manifest.db_sha256`, restores `l1/archivum.db` to `settings.db_path`
     and `l0/*` into the blob store, then `await rebuild(settings)`.
  - `async def rebuild_indexes_from_l1(settings: Settings) -> dict[str, int]` — headless
     version of `api/system.py::rebuild_indexes` (no auth dep) that re-inits Qdrant + Kuzu
     + FTS and re-projects all L1 rows. `api/system.py::rebuild_indexes` is refactored to
     call this.
- Consumes: Task 4 dump output, `db.qdrant_client.init_collection`, `db.graph.init_graph`.

Steps:
- [ ] Refactor `rebuild_indexes` core into `rebuild_indexes_from_l1(settings)` in
      `backup.py`; have `api/system.py::rebuild_indexes` call it. Run existing
      `tests/api/test_system.py` → PASS (no behavior change).
- [ ] Write `test_backup_roundtrip`: seed 3 pages + entities, dump, wipe db + L2 dirs,
      `restore_backup(...)` with a real `rebuild_indexes_from_l1`, then assert
      `sqlite.list_pages()` returns the same 3 pages AND a FTS query
      (`sqlite.search_pages_fts`) returns a rebuilt hit — proving L2 was regenerated from L1.
- [ ] Run → FAIL (`restore_backup` missing).
- [ ] Implement `restore_backup` (decrypt → verify sha → extract → rebuild). Run → PASS.
- [ ] Add `test_restore_rejects_corrupt_manifest` (flip a byte in the tarred db, expect
      `ValueError` on sha mismatch). Add `python -m archivum.backup restore --archive`
      `__main__` branch. Run → PASS.
- [ ] Commit: `feat(backup): restore L0+L1 and rebuild L2 indexes`

### Task 6 — Backup integrity: query-result round-trip

**Files:** `tests/backup/test_backup_roundtrip.py` (extend)

**Interfaces:**
- Consumes: `backup.dump_backup`, `backup.restore_backup`,
  `retrieval` shim (Task 8) OR direct `sqlite.search_pages_fts` if Task 8 not yet done —
  use FTS to keep this task self-contained.

Steps:
- [ ] Add `test_roundtrip_reproduces_query_results`: seed a corpus of 5 pages with known
      content; run `sqlite.search_pages_fts("archivum", limit=5)` and capture the ordered
      slug list `before`. Dump → wipe db+L2 → restore. Run the same query, capture `after`.
      Assert `before == after` (same slugs, same order) — proving restore reproduces
      retrieval results, not just row counts.
- [ ] Run → FAIL (assertion or restore path not exercising rebuild).
- [ ] Fix any ordering nondeterminism by making `rebuild_indexes_from_l1` iterate pages in
      a stable `ORDER BY id` (adjust `list_pages`/local query as needed). Run → PASS.
- [ ] Add `test_roundtrip_with_encryption`: same flow but `dump_backup`/`restore_backup`
      pass a real `Encryptor` derived from a passphrase. Run → PASS.
- [ ] Commit: `test(backup): verify round-trip reproduces query results`

### Task 7 — Scope model + columns migration

**Files:** `apps/backend/archivum/scope.py`,
`apps/backend/archivum/migrations/m0001_scope_columns.py`,
`tests/scope/test_scope_model.py`

**Interfaces:**
- Produces:
  - `class Scope(BaseModel): label: str` with validator: label matches
    `^(personal|work|repo:[a-z0-9_-]+|shared)$`.
  - `def parse_scopes(raw: str | list[str]) -> set[str]` — normalize CSV/list to a set.
  - `def scopes_for_role(role: str, owner_scopes: set[str]) -> set[str]` — `owner` gets
    all; others get intersection with an allow-list (single-owner: non-owner → `{}`).
  - `DEFAULT_SCOPE = "personal"`.
- Consumes: none (pure). Migration adds `scope TEXT NOT NULL DEFAULT 'personal'` to
  `pages` (and future knowledge tables) — the migration body is exercised via Task 11.

Steps:
- [ ] Write `tests/scope/__init__.py` + `test_scope_model.py::test_valid_and_invalid_labels`:
      `Scope(label="repo:archivum")` ok; `Scope(label="bad space")` raises
      `pydantic.ValidationError`.
- [ ] Run → FAIL (module missing).
- [ ] Implement `Scope`, `parse_scopes`, `scopes_for_role`, `DEFAULT_SCOPE`. Run → PASS.
- [ ] Add `test_scopes_for_role`: `scopes_for_role("owner", {"personal","work"})` returns
      both; `scopes_for_role("viewer", {"personal","work"})` returns `set()`.
      Run → PASS.
- [ ] Create `migrations/m0001_scope_columns.py` exposing
      `VERSION = 1` and `async def up(db)` that runs
      `ALTER TABLE pages ADD COLUMN scope TEXT NOT NULL DEFAULT 'personal'` guarded by a
      `PRAGMA table_info` check (idempotent). No test yet (covered in Task 11).
- [ ] Commit: `feat(scope): add Scope model and scope-column migration`

### Task 8 — Retrieval shim + scope enforcement filter

**Files:** `apps/backend/archivum/scope.py` (extend),
`apps/backend/archivum/retrieval.py` (thin shim), `tests/scope/test_scope_enforcement.py`

**Interfaces:**
- Produces:
  - `def enforce_scope(rows: list[dict], allowed: set[str]) -> list[dict]` — drop any row
    whose `scope` not in `allowed`; owner sentinel `{"*"}` allows all.
  - `async def scoped_page_search(query: str, allowed: set[str], wiki_id: str = "default",
     limit: int = 10) -> list[dict]` in `retrieval.py` — calls
     `sqlite.search_pages_fts` then `enforce_scope`. (This is the swap point for PER-319.)
- Consumes: `sqlite.search_pages_fts`, `scope.enforce_scope`.

Steps:
- [ ] Write `test_enforce_scope_filters`: given rows with scopes
      `["personal","work","personal"]` and `allowed={"personal"}`, result has 2 rows, all
      `scope == "personal"`; `allowed={"*"}` returns all 3.
- [ ] Run → FAIL (function missing).
- [ ] Implement `enforce_scope`. Run → PASS.
- [ ] Write `test_scoped_page_search_excludes_other_scopes`: seed pages tagged
      (via the `scope` column from Task 7's migration applied in the test's db init) with
      `personal` and `work`; assert `scoped_page_search("secret", {"personal"})` never
      returns the `work` page even when it matches the query text.
- [ ] Run → FAIL (`retrieval.scoped_page_search` missing / column absent).
- [ ] Implement `scoped_page_search` in `retrieval.py`; ensure the test applies migration
      `m0001` before seeding. Run → PASS.
- [ ] Commit: `feat(retrieval): scope-enforced page search shim`

### Task 9 — Scope access-control middleware + API isolation

**Files:** `apps/backend/archivum/scope.py` (extend),
`apps/backend/archivum/api/search.py` (wire enforcement),
`tests/scope/test_scope_api_isolation.py`

**Interfaces:**
- Produces:
  - `def allowed_scopes_for_user(user: CurrentUser, requested: str | None) -> set[str]` —
    owner → `{"*"}`; otherwise intersect requested with the user's granted scopes
    (single-owner: default deny → `{}`).
  - Search endpoint accepts optional `?scope=` and passes
    `allowed_scopes_for_user(current_user, scope)` into `scoped_page_search`.
- Consumes: `auth.CurrentUser`, `retrieval.scoped_page_search`.

Steps:
- [ ] Write `test_scope_api_isolation` (FastAPI `TestClient` + owner token, following
      `tests/api/test_search.py` patterns): seed a `work`-scoped page and a `personal`-scoped
      page; owner querying with `?scope=personal` gets only the personal page; querying
      `?scope=work` gets only the work page — proving cross-scope isolation through the API.
- [ ] Run → FAIL (endpoint ignores scope).
- [ ] Implement `allowed_scopes_for_user`; wire the `scope` query param through
      `api/search.py` into `scoped_page_search`. Run → PASS.
- [ ] Add `test_non_owner_default_deny`: a `viewer`-role token querying without an allowed
      scope receives zero rows (single-owner default-deny). Run → PASS.
- [ ] Commit: `feat(scope): enforce cross-scope isolation at the API`

### Task 10 — Observability: metrics + health endpoints

**Files:** `apps/backend/archivum/metrics.py`,
`apps/backend/archivum/observability.py` (extend),
`apps/backend/archivum/api/health.py`, `apps/backend/archivum/main.py` (register router),
`tests/observability/test_metrics.py`, `tests/observability/test_health.py`

**Interfaces:**
- Produces:
  - `class Metrics:` `incr(self, name: str, by: int = 1) -> None`;
    `observe(self, name: str, value_ms: float) -> None`;
    `snapshot(self) -> dict[str, dict]` (per-name: `count`, `sum_ms`, `p50_ms`, `p95_ms`).
  - `METRICS: Metrics` module singleton.
  - `@contextmanager def timed(name: str)` in `observability.py` — records duration into
    `METRICS.observe(name, ...)` (wraps existing `span`).
  - Router in `api/health.py`:
    - `GET /api/health` → `{"status":"ok","version":...}` (liveness, no auth).
    - `GET /api/health/ready` → checks SQLite + Qdrant reachable; 200 or 503.
    - `GET /api/metrics` (owner-only) → `METRICS.snapshot()`.
- Consumes: `db.sqlite.get_db`, `db.qdrant_client`, `auth.require_owner`.

Steps:
- [ ] Write `tests/observability/__init__.py` + `test_metrics.py::test_counter_and_hist`:
      `m = Metrics(); m.incr("ingest.docs"); m.observe("ingest.ms", 10); m.observe(...,20)`
      then assert `snapshot()["ingest.docs"]["count"] == 1` and `ingest.ms` p50 present.
- [ ] Run → FAIL (module missing).
- [ ] Implement `Metrics` (deque-bounded histograms, percentile calc) + `METRICS`.
      Run → PASS.
- [ ] Add `timed` to `observability.py` (delegates to `span`, then
      `METRICS.observe`). Add unit test `test_timed_records` (elapsed recorded under name).
      Run → PASS.
- [ ] Write `test_health.py::test_liveness_and_metrics` using `TestClient`: `/api/health`
      → 200 `{"status":"ok"}`; `/api/metrics` without owner token → 401/403.
- [ ] Run → FAIL (router not mounted).
- [ ] Implement `api/health.py` router (liveness/readiness/metrics) and
      `app.include_router` it in `main.py`. Run → PASS.
- [ ] Instrument the ingest path: in `ingest/pipeline.py::ingest`, call
      `METRICS.incr("ingest.sources")` on start and `METRICS.incr("ingest.pages_created",
      pages_created)` at the end; wrap extraction in `timed("ingest.extract")`. Add
      `test_ingest_increments_metrics` (run a stubbed ingest, assert counters moved). Run → PASS.
- [ ] Commit: `feat(observability): add metrics registry and health endpoints`

### Task 11 — Migration runner + versioned migrations

**Files:** `apps/backend/archivum/migrations/__init__.py`,
`apps/backend/archivum/migrations/runner.py`,
`apps/backend/archivum/db/sqlite.py` (call runner in `init_db`),
`tests/migrations/test_runner.py`

**Interfaces:**
- Produces:
  - `class Migration(Protocol): VERSION: int; async def up(self, db) -> None`
  - `MIGRATIONS: list` — ordered `[m0001_scope_columns, m0002_ingest_checkpoints]`.
  - `async def current_version(db) -> int` — reads `schema_migrations` table (creates it
    if absent), returns max applied version or 0.
  - `async def apply_migrations(db) -> list[int]` — applies each pending migration in a
    transaction, records `(version, applied_at)`; returns list of newly-applied versions.
- Consumes: `db.sqlite.get_db`.

Steps:
- [ ] Write `tests/migrations/__init__.py` + `test_runner.py::test_apply_is_idempotent`:
      against a fresh temp db, `apply_migrations(db)` returns `[1, 2]`; a second call
      returns `[]` and `current_version(db) == 2`.
- [ ] Run → FAIL (runner missing).
- [ ] Implement `schema_migrations` table bootstrap, `current_version`, `apply_migrations`
      (transaction per migration; on error, rollback + re-raise). Register `m0001` and a
      stub `m0002` (`VERSION = 2`, no-op `up` for now). Run → PASS.
- [ ] Add `test_version_column_present` (after apply, `PRAGMA table_info(pages)` includes
      `scope`). Run → PASS.
- [ ] Call `await apply_migrations(db)` inside `sqlite.init_db` after `executescript`.
      Run existing `tests/db/test_sqlite.py` → PASS (schema still valid).
- [ ] Commit: `feat(migrations): add versioned schema migration runner`

### Task 12 — Forward-migration test with real data

**Files:** `tests/migrations/test_forward_migration.py`

**Interfaces:** Consumes `migrations.runner.apply_migrations`, `db.sqlite`.

Steps:
- [ ] Write `test_forward_migration_preserves_data`: create a temp db with the PRE-scope
      `pages` schema (no `scope` column) and insert 2 rows; run `apply_migrations(db)`;
      assert both rows survive AND now have `scope == 'personal'` (the column default), and
      `current_version(db) == 2`.
- [ ] Run → FAIL if migration is destructive or default missing.
- [ ] Fix `m0001` so the `ADD COLUMN` default backfills existing rows (SQLite applies the
      `DEFAULT` to existing rows for `NOT NULL DEFAULT`). Run → PASS.
- [ ] Add `test_migration_from_arbitrary_version`: pre-seed `schema_migrations` with
      `version=1` applied, then `apply_migrations` applies only `[2]`. Run → PASS.
- [ ] Commit: `test(migrations): verify forward migration preserves data`

### Task 13 — Failure recovery: resumable ingest checkpoints

**Files:** `apps/backend/archivum/migrations/m0002_ingest_checkpoints.py`,
`apps/backend/archivum/ingest/checkpoint.py`,
`apps/backend/archivum/ingest/pipeline.py` (wire checkpoints),
`tests/ingest/test_checkpoint_resume.py`

**Interfaces:**
- Produces:
  - Migration `m0002` `up`: create
    `ingest_checkpoints(source_hash TEXT PRIMARY KEY, stage TEXT NOT NULL,
    last_page_slug TEXT, updated_at TEXT)`.
  - In `checkpoint.py`:
    - `async def get_checkpoint(source_hash: str) -> dict | None`
    - `async def set_checkpoint(source_hash: str, stage: str, last_page_slug: str | None)
       -> None`
    - `async def clear_checkpoint(source_hash: str) -> None`
    - `def source_hash(source: str) -> str` — sha256 of the source identifier.
- Consumes: `db.sqlite.get_db`.

Steps:
- [ ] Flesh out `m0002_ingest_checkpoints.py` `up` (replace the Task 11 stub) creating the
      table idempotently.
- [ ] Write `tests/ingest/test_checkpoint_resume.py::test_checkpoint_crud`: set → get
      returns stage + slug; clear → get returns `None`.
- [ ] Run → FAIL (module missing).
- [ ] Implement `checkpoint.py` CRUD + `source_hash`. Run → PASS.
- [ ] Wire into `ingest/pipeline.py::ingest`: at start compute `source_hash`, if a
      checkpoint with `stage == 'persisted'` exists skip already-written page slugs; after
      each page upsert call `set_checkpoint(h, "persisted", final_slug)`; on successful
      completion `clear_checkpoint(h)`.
- [ ] Write `test_resume_skips_completed_pages`: simulate an interrupted ingest by
      pre-seeding a checkpoint at `last_page_slug` for a 3-page fixture, run `ingest`, and
      assert pages already recorded are not re-created (assert `pages_created` counts only
      the remaining pages). Run → FAIL then PASS after wiring.
- [ ] Commit: `feat(ingest): resumable checkpoints for interrupted ingest`

### Task 14 — Failure recovery: partial index rebuild

**Files:** `apps/backend/archivum/backup.py` (extend `rebuild_indexes_from_l1`),
`tests/ingest/test_partial_rebuild.py`

**Interfaces:**
- Produces:
  - `async def rebuild_indexes_from_l1(settings: Settings, only: set[str] | None = None,
     since_slug: str | None = None) -> dict[str, int]` — `only ⊆ {"qdrant","kuzu","fts"}`
     selects which L2 stores to rebuild; `since_slug` resumes projection from a slug
     (stable id order) so a crashed rebuild continues instead of restarting.
- Consumes: `db.qdrant_client`, `db.graph`, `db.sqlite`.

Steps:
- [ ] Write `test_partial_rebuild_only_fts`: seed 3 pages, drop FTS content, call
      `rebuild_indexes_from_l1(settings, only={"fts"})`, assert FTS query returns hits and
      the function reports `{"fts": 3}` while `qdrant`/`kuzu` are untouched (0 or absent).
- [ ] Run → FAIL (signature lacks `only`).
- [ ] Extend `rebuild_indexes_from_l1` with `only`/`since_slug` gating (default keeps
      full-rebuild behavior for Task 5). Run → PASS.
- [ ] Add `test_rebuild_resumes_since_slug`: with a stable `ORDER BY id`, calling with
      `since_slug` of the 2nd page projects only pages after it (assert count == remaining).
      Run → PASS.
- [ ] Re-run `tests/backup/test_backup_roundtrip.py` to confirm no regression. → PASS.
- [ ] Commit: `feat(recovery): support partial and resumable index rebuild`

### Task 15 — Backup/restore ops scripts

**Files:** `scripts/backup.sh`, `scripts/restore.sh`, `Makefile`,
`docs/ops/backup-restore.md`, `tests/backup/test_backup_scripts.py`

**Interfaces:**
- Produces:
  - `scripts/backup.sh` — `set -euo pipefail`, `cd` to repo root, run
    `cd apps/backend && uv run python -m archivum.backup dump --out "$1"`; prints the
    written archive path. Matches existing `install.sh`/`update.sh` header style.
  - `scripts/restore.sh` — same pattern, calls `python -m archivum.backup restore
    --archive "$1"`; refuses to run if archive missing (exit 1 with message).
  - `Makefile` targets `backup` and `restore` delegating to the scripts.
- Consumes: Task 4/5 `__main__` entrypoints.

Steps:
- [ ] Write `tests/backup/test_backup_scripts.py::test_backup_script_creates_archive`:
      `subprocess.run(["bash","scripts/backup.sh", out], ...)` against a temp
      `DB_PATH`/`BLOB` env, assert exit 0 and the archive file exists and is a valid gzip.
- [ ] Run → FAIL (script missing).
- [ ] Write `scripts/backup.sh` (executable, `chmod +x`) matching repo header conventions.
      Run → PASS.
- [ ] Add `test_restore_script_round_trip`: backup then
      `bash scripts/restore.sh <archive>` into a wiped data dir, assert exit 0 and the db
      file exists. Write `scripts/restore.sh`. Run → PASS.
- [ ] Add `backup:` / `restore:` targets to `Makefile` (mirroring `rebuild-indexes`
      guard) and write `docs/ops/backup-restore.md` runbook (what's precious vs
      rebuildable, cron example, encryption note). No test for docs.
- [ ] Commit: `feat(ops): add backup/restore scripts and runbook`

### Task 16 — Deployment hardening: backup volume + healthcheck

**Files:** `docker-compose.yml`, `caddy/Caddyfile`,
`tests/backup/test_compose_config.py`

**Interfaces:**
- Produces:
  - New named volume `backup_data:/data/backups` mounted on `backend` (precious).
  - Backend `healthcheck` hitting `GET /api/health` (uses Task 10 endpoint).
  - Env passthrough for `BACKUP_ENCRYPTION_ENABLED`, `BACKUP_PASSPHRASE`, `BACKUP_DIR`,
    `LOG_LEVEL` on `backend` + `mcp`.
- Consumes: existing compose structure.

Steps:
- [ ] Write `tests/backup/test_compose_config.py::test_compose_has_backup_volume`: parse
      `docker-compose.yml` with `yaml.safe_load`, assert `backup_data` in top-level
      `volumes` and mounted on `services.backend.volumes`, and that `qdrant_data`/`kuzu_data`
      are NOT listed under any backup-related mount (they remain rebuildable).
- [ ] Run → FAIL (volume absent).
- [ ] Add `backup_data` volume + mount + the three backup env vars + `LOG_LEVEL` to
      `backend` and `mcp` in `docker-compose.yml`. Run → PASS.
- [ ] Add `test_backend_has_healthcheck`: assert `services.backend.healthcheck.test`
      references `/api/health`. Add the healthcheck block (curl/wget against
      `http://127.0.0.1:8000/api/health`). Run → PASS.
- [ ] Commit: `feat(deploy): add backup volume and backend healthcheck`

### Task 17 — Dogfooding fixture corpus + ingest harness

**Files:** `tests/dogfood/fixtures/` (docs + conversations + a small repo),
`apps/backend/archivum/dogfood/__init__.py`,
`apps/backend/archivum/dogfood/harness.py`, `tests/dogfood/test_harness.py`

**Interfaces:**
- Produces:
  - Fixtures: `fixtures/docs/*.md` (≥3 real notes), `fixtures/conversations/*.txt`
    (≥2 chat transcripts), `fixtures/repo/` (a tiny Python package: 2 `.py` files with
    imports/calls so code has real structure).
  - `class IngestReport(BaseModel): sources: int; pages_created: int; entities: int;
     errors: list[str]`
  - `async def ingest_corpus(root: Path, settings: Settings) -> IngestReport` — walks the
    fixture tree, ingests each source via `ingest.pipeline.ingest`, aggregates counts.
- Consumes: `ingest.pipeline.ingest`, `metrics.METRICS`.

Steps:
- [ ] Create the fixture corpus files (real content: e.g. a project-decision note that
      references a person and a repo; two conversation transcripts discussing that
      decision; a 2-file repo whose modules import each other).
- [ ] Write `tests/dogfood/__init__.py` + `test_harness.py::test_ingest_corpus_counts`
      (may stub the LLM extractor to a deterministic fake to avoid network — assert
      `ingest_corpus` returns `sources == <fixture count>`, `errors == []`).
- [ ] Run → FAIL (harness missing).
- [ ] Implement `IngestReport` + `ingest_corpus`. Run → PASS.
- [ ] Add `test_corpus_covers_all_source_types` (report includes at least one doc, one
      conversation, one code source). Run → PASS.
- [ ] Commit: `feat(dogfood): fixture corpus and ingest harness`

### Task 18 — Retrieval-quality eval: correctness, insufficient-evidence, token size

**Files:** `apps/backend/archivum/dogfood/eval.py`,
`tests/dogfood/questions.json`, `tests/dogfood/test_retrieval_eval.py`

**Interfaces:**
- Produces:
  - `class QAItem(BaseModel): question: str; expected_slugs: list[str];
     answerable: bool` (loaded from `questions.json`).
  - `class EvalResult(BaseModel): total: int; cited_correct: int;
     insufficient_correct: int; avg_context_tokens: float; max_context_tokens: int`
  - `def approx_tokens(text: str) -> int` — `len(text)//4` heuristic (documented).
  - `async def run_eval(items: list[QAItem], settings: Settings) -> EvalResult` — for each
    item, build a scoped context package via `retrieval.scoped_page_search` (owner scope),
    check that at least one `expected_slug` is cited for answerable items, and that
    unanswerable items yield an empty/insufficient result (spec §6.5 "insufficient
    evidence" rather than fabrication); measure context token size via `approx_tokens`.
- Consumes: `retrieval.scoped_page_search`, `dogfood.harness.ingest_corpus`.

Steps:
- [ ] Author `tests/dogfood/questions.json`: ≥4 answerable questions (each with
      `expected_slugs` grounded in the fixtures) + ≥2 unanswerable questions
      (`answerable: false`, `expected_slugs: []`).
- [ ] Write `test_retrieval_eval.py::test_eval_cited_correctness`: ingest the corpus
      (Task 17 harness with the deterministic fake extractor), `run_eval(items)`, assert
      `cited_correct == <answerable count>` (every answerable question surfaces an expected
      slug).
- [ ] Run → FAIL (eval missing).
- [ ] Implement `QAItem`, `EvalResult`, `approx_tokens`, `run_eval`. Run → PASS.
- [ ] Add `test_insufficient_evidence`: assert unanswerable questions produce
      `insufficient_correct == <unanswerable count>` (empty context / no fabricated slug).
      Run → PASS.
- [ ] Add `test_context_token_budget`: assert `EvalResult.max_context_tokens` is below a
      budget constant (e.g. `2000`) — proving the context package stays token-bounded per
      spec §8. Run → PASS.
- [ ] Commit: `feat(dogfood): retrieval-quality eval with token + evidence checks`

---

## Self-Review

**Spec coverage:**
- §2 volume/precious-vs-rebuildable → Tasks 4 (dump L0+L1), 5 (restore + rebuild L2),
  16 (backup volume added; qdrant/kuzu stay rebuildable). ✔
- §4 scope & query-time enforcement → Tasks 7 (model+migration), 8 (filter), 9 (API
  isolation). ✔
- §6 trust invariants: (6.1) L0 immutable/content-addressed → Task 1; (6.5) insufficient
  evidence → Task 18; (6.6) L2/L3 regenerable from L1 → Tasks 5, 6, 14. ✔
- §9 migration (evolve in place, reshape schema) → Tasks 11, 12, 13. ✔
- Encryption + secrets → Tasks 2, 3. Observability → Task 10. Failure recovery → Tasks 13,
  14. Dogfooding + eval → Tasks 17, 18. ✔

**Placeholder scan:** No `TODO`/stub-only implementations. The only intentional stub is
`m0002` in Task 11, explicitly replaced with a real table in Task 13. The `retrieval.py`
shim (Task 8) is real (FTS-backed) and documented as the PER-319 swap point.

**Type consistency:** `BackupManifest` produced in Task 4, consumed in Task 5.
`Encryptor` produced in Task 2, consumed in Tasks 4/5. `Scope`/`enforce_scope`/
`scopes_for_role` from Tasks 7–8 consumed in Task 9. `Metrics`/`METRICS` from Task 10
consumed in Tasks 10/17. `Migration`/`apply_migrations`/`current_version` from Task 11
consumed in Tasks 4 (schema_version), 12, 13. `rebuild_indexes_from_l1` produced in Task 5,
extended in Task 14, consumed in Tasks 5/6/14. `ingest_corpus`/`IngestReport` from Task 17
consumed in Task 18. `scoped_page_search` from Task 8 consumed in Tasks 9 and 18.

**Dependency ordering:** Migration runner (Task 11) is referenced by Task 4's
`schema_version` and Task 7's migration file; Task 7 authors the migration module but the
runner that applies it lands in Task 11, and every test that needs the `scope` column
(Tasks 8, 9) applies `m0001` explicitly in its db setup — so no task depends on an
unapplied migration. Fixed inline: Task 8/9 steps state that migrations are applied in
test setup.
