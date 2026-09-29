# Campus Lost & Found API

A REST service for reporting, searching, and reuniting lost property on a
university campus. **FastAPI + PostgreSQL**, containerised with Docker Compose.

Items move through an explicit lifecycle:

```
reported  ->  matched  ->  claimed  ->  closed
```

`closed` is terminal. Illegal moves are rejected by the service layer, and every
transition is appended to an audit table rather than overwriting the previous state.
Claims drive most of the moves: filing one moves a `reported` item to `matched`,
approving one moves it to `claimed`, and rejecting the last open one sends it back
to `reported` (see [Claims](#claims)). The web UI shows `matched` as **"Claim
pending"**; the API value stays `matched`.

---

## Stack

| Concern        | Choice                                              |
| -------------- | --------------------------------------------------- |
| Web framework  | FastAPI 0.115 (OpenAPI docs at `/docs`)             |
| Validation     | Pydantic v2 — every route has a request schema and a `response_model` |
| Database       | PostgreSQL 16 (**only** — no SQLite/MySQL fallback) |
| ORM / driver   | SQLAlchemy 2.0 + psycopg 3                          |
| Search         | `ILIKE` over `pg_trgm` GIN indexes                  |
| Auth           | JWT bearer tokens, bcrypt password hashing          |
| Migrations     | Alembic — the source of truth for the schema        |
| Browser UI     | Plain HTML/CSS/vanilla JS, no build step, served at `/app/` |
| Packaging      | Docker Compose (`api` + `db`)                       |

---

## Quick start

The whole stack — API and database — comes up with one command. No local
PostgreSQL install is needed; the database runs in its own container. The
container entrypoint runs `alembic upgrade head` before starting uvicorn, so the
API only ever reports healthy once the schema is up to date.

```bash
docker compose up --build
```

Then:

* Web UI — <http://localhost:8000/app/>
* API — <http://localhost:8000>
* Interactive docs — <http://localhost:8000/docs>
* Health check — <http://localhost:8000/health>

```console
$ curl http://localhost:8000/health
{"status":"ok","database":"reachable","version":"1.0.0"}
```

Tear down, including the database volume:

```bash
docker compose down -v
```

### Configuration

Copy the example file and edit it. **Never commit a real `.env`** — it is
gitignored.

```bash
cp .env.example .env
```

`DATABASE_URL` is required and must be a PostgreSQL URL. There is no fallback:
pointing it at `sqlite://` or `mysql://` is a startup error, by design, so the
service can never quietly run on a different engine than the one it was built for.

---

## Running without Docker

You still need a PostgreSQL 16 server reachable from your machine.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
export DATABASE_URL=postgresql://lostfound:lostfound@localhost:5432/lostfound
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(48))")
uvicorn app.main:app --reload
```

Apply the schema before first run:

```bash
alembic upgrade head
```

Alembic reads `DATABASE_URL` from the same settings object the app uses — the
connection string is not duplicated in `alembic.ini`. Set
`RUN_MIGRATIONS_ON_STARTUP=true` if you would rather the app process migrate
itself on boot while using `--reload`.

---

## Demo data

A fresh deployment is empty. To give visitors something to browse, seed it with
realistic campus data: 8 locations, 8 categories, 6 demo accounts, 33 lost and
found items spread across every lifecycle state, and 9 claims (pending, approved
and rejected). Four of the lost reports have a matching found post from someone
else, so the item page's "Possible matches" panel has results to show.

```bash
docker compose exec api python scripts/seed_demo.py           # seed
docker compose exec api python scripts/seed_demo.py --reset   # remove it again
```

The script goes through the service layer, so every item gets the same status
history and notifications it would get through the API. It is safe to run
repeatedly: anything already present is skipped. It prints the demo logins and
their shared password (`campus-demo-2026`) at the end.

The demo accounts all use `@example.com` addresses, so no real person is ever
emailed. They are verified and are not admins. `--reset` deletes exactly those
accounts, and their items, claims and notifications go with them by cascade.
Locations and categories stay, because real items may use them too.

---

## API

| Method | Path                        | Purpose                              |
| ------ | --------------------------- | ------------------------------------ |
| GET    | `/health`                   | Liveness + database reachability     |
| POST   | `/auth/register`            | Create an account, issue an OTP      |
| POST   | `/auth/verify-registration` | Confirm the account with its OTP     |
| POST   | `/auth/login`               | Exchange credentials for a JWT       |
| POST   | `/auth/password-reset/request` | Send a reset OTP                  |
| POST   | `/auth/password-reset/confirm` | Set a new password                |
| GET    | `/auth/me`                  | Current user                         |
| POST   | `/items`                    | **Register** a lost/found item       |
| GET    | `/items`                    | **Search** items                     |
| GET    | `/items/{id}`               | One item plus its lifecycle history  |
| GET    | `/items/{id}/suggestions`   | Possible matches of the opposite kind |
| PATCH  | `/items/{id}`               | Edit descriptive fields              |
| POST   | `/items/{id}/status`        | **Transition** lifecycle state       |
| DELETE | `/items/{id}`               | Delete an item you reported          |
| POST   | `/items/{id}/claims`        | File a claim                         |
| GET    | `/claims`                   | List claims                          |
| POST   | `/claims/{id}/decision`     | Approve or reject a claim            |
| GET/POST | `/locations`              | Campus locations                     |
| GET/POST | `/categories`             | Item categories                      |
| GET    | `/notifications`            | Your notifications                   |
| GET    | `/admin/stats`              | Row counts (**admin**)               |
| GET    | `/admin/users`              | List/search every account (**admin**)|
| POST   | `/admin/users/{id}/role`    | Grant or revoke staff (**admin**)    |
| DELETE | `/admin/users/{id}`         | Delete an account (**admin**)        |
| DELETE | `/admin/items/{id}`         | Delete any item (**admin**)          |
| POST   | `/admin/items/bulk-delete`  | Delete up to 500 items (**admin**)   |
| DELETE | `/admin/locations/{id}`     | Delete a location (**admin**)        |
| DELETE | `/admin/categories/{id}`    | Delete a category (**admin**)        |

Search accepts `q`, `category_id`, `location_id`, `status`, `kind`,
`reporter_id`, `limit`, `offset` — all validated by a Pydantic model, so query
strings are typed the same way request bodies are.

### Who can see and do what

Ownership, not roles, drives the ordinary rules: you may edit and transition the
items **you** reported, and decide the claims filed against them. Two things are
narrower than that:

* **Claims are private to the two people they are between** — the claimant and
  the item's reporter. The `evidence` field is where people put serial numbers
  and receipts, so `GET /claims?item_id=` on a stranger's item returns nothing
  rather than handing that out.
* **Contact details are disclosed on approval only.** Item and claim responses
  carry a name, never an address, until a claim between the two parties is
  approved — at which point each sees the other's `contact_email` so they can
  arrange the handover. Withdrawing the approval takes it away again, because
  the condition is re-evaluated on every read rather than stored.

`is_admin` is the one role. It exists because the lifecycle otherwise has no
oversight at all: a reporter decides the claims on their own item, so a wrong
decision has nobody to correct it. An admin may manage any item, read and decide
any claim, curate locations and categories, and administer accounts.

The first admin has to be made out-of-band — `/admin/users/{id}/role` needs an
admin to call it, so there would be no way in otherwise:

```bash
docker compose exec api python scripts/make_admin.py you@example.com
docker compose exec api python scripts/make_admin.py --list
docker compose exec api python scripts/make_admin.py you@example.com --revoke
```

After that, admins promote each other from `/app/admin.html`. Two guards apply
even to staff: you cannot demote or delete yourself, and deleting another admin
requires revoking their access first — so the system cannot be left with no
administrator by a single misclick.

### Claims

One item can have many claims but **at most one approved claim**, because approval
is what discloses contact details.

* **Approving a claim rejects every other pending claim** on the item in the same
  transaction, and each of those claimants is notified that another claim was
  approved.
* **A second approval is refused** with `409` while one stands. That applies to
  admins too. A claim can still be filed on a `claimed` item, but it cannot be
  approved until the standing approval is withdrawn. Filing it does not move the
  item.
* **The database enforces it as well.** A partial unique index
  (`uq_claims_one_approved_per_item`) allows one `approved` row per item, so a
  race between two approvals ends in a `409`, not two disclosures.
* **Approval needs a `matched` item.** Approving is the `matched` → `claimed`
  step, so it is refused (`409`) on an item in any other state, even if a
  pending claim exists there.
* **Rejecting the last open claim relists the item.** If a rejection leaves a
  `matched` item with no pending or approved claim, it goes back to `reported`
  with the history note "All claims rejected." If other claims are still pending,
  it stays `matched`. Relisting by hand (`matched` → `reported`) is refused
  (`409`) while any claim is pending: decide them first, and the last rejection
  relists the item on its own.
* **Withdrawing an approval reopens the claims it pushed out.** Moving an item
  from `claimed` back to `matched` sends the approved claim back to `pending`,
  which removes the contact details it had disclosed. It also reopens every claim
  that approval auto-rejected (tracked in `claims.superseded_by_id`), because
  they lost to that claim rather than on their own merits. Decisions are
  one-shot, so leaving them rejected would lock out what may be the real owner.
  Claims that were rejected directly stay rejected, and closing a `claimed` item
  changes no claims.

### Match suggestions

`GET /items/{id}/suggestions` lists up to 5 open items of the **opposite kind**
(a lost report gets found items, and vice versa), leaving out closed items and
the reporter's own posts. A closed item gets no suggestions.

Candidates are ranked by `pg_trgm` similarity: 60% name-to-name, 40% full text
(name + description) to full text. Names carry more weight because descriptions
are prose, and unrelated prose already scores 0.15–0.25 on shared common words.
Anything below **0.25** is dropped. Boosts are added only after that cut-off, so
they can never promote an unrelated item: **+0.10** for the same category,
**+0.05** for the same location, and **+0.05** for a date within ±14 days. Each
result carries `score`, `similarity` and the `reasons` it was boosted. Results
use the same public item fields as search, so they never include contact details.

This scores every open item of the opposite kind. A filter on a computed score
cannot use the trigram GIN indexes, so it has not been tuned for very large
tables.

### Email / OTP delivery

Two modes, switched by `MAIL_ENABLED`:

| | `MAIL_ENABLED=false` (default) | `MAIL_ENABLED=true` |
| --- | --- | --- |
| Delivery | nothing sent, message logged | real SMTP (STARTTLS) |
| `otp_debug` in response | the live code | **always `null`** |
| Used by | local dev, CI, the Playwright e2e test | production |

For Gmail, set `MAIL_SERVER=smtp.gmail.com`, `MAIL_PORT=587`, and make
`MAIL_PASSWORD` a **16-character App Password**
(<https://myaccount.google.com/apppasswords>, requires 2-Step Verification) —
a normal account password is rejected with SMTP 535. `MAIL_FROM` must match
`MAIL_USERNAME`, since Gmail refuses to send as an unverified address.

**Security invariant.** `otp_debug` is exposed if and only if outbound mail is
*disabled*. It is keyed on `EmailService.enabled`, never on whether a given send
succeeded — keying it on the delivery result would hand a live OTP to the API
caller at precisely the moment SMTP broke. `tests/test_email.py` locks this in,
and `scripts/verify_otp_exposure.py` prints both response bodies side by side.

Send failures are explicit, never silent: they raise `MailDeliveryError`
(HTTP 502) with an actionable message, log the server's response, and roll the
transaction back, so a failed send does not leave an unverifiable account behind.

```bash
python scripts/verify_otp_exposure.py                       # both modes, side by side
python scripts/send_test_email.py you@example.com           # real send + SMTP transcript
```

---

## Web UI

A small browser client is served by FastAPI's `StaticFiles` at **`/app/`**:

| Page | Purpose |
| ---- | ------- |
| `/app/index.html` | Browse and search items |
| `/app/item.html?id=N` | Item detail, lifecycle history, claims, transitions, possible matches |
| `/app/report.html` | Report a lost/found item |
| `/app/claims.html` | Claims on your items, and claims you filed |
| `/app/login.html`, `register.html`, `verify.html` | Auth + OTP verification |
| `/app/reset-request.html`, `reset-confirm.html` | Password reset |
| `/app/admin.html` | Staff console: items, accounts, locations, categories |

Deliberately plain: no framework, no build step, no npm. `frontend/js/api.js`
is the only place that talks to the API — it attaches the bearer token, turns
the API's typed error envelope into per-field form errors, and redirects to
login on a 401. Because the UI is same-origin under `/app/`, there is no CORS
configuration anywhere.

The UI is **purely additive**: mounting it changed no route, no schema, and no
response model. `/openapi.json` is byte-identical before and after.

In dev (`MAIL_ENABLED=false`) the register and password-reset endpoints return
the one-time code as `otp_debug` rather than emailing it, and the UI displays it
so the flow is completable without an SMTP server.

### End-to-end browser test

`scripts/e2e_test.py` drives a real Chromium against the running compose stack —
two separate users in separate browser contexts — through the whole path:
register → verify OTP → login → report → search → claim → approve → close.

```bash
pip install -r requirements-dev.txt
python -m playwright install chromium
docker compose up -d
python scripts/e2e_test.py
```

It makes **35 assertions** and exits non-zero if any fails; screenshots land in
`scripts/e2e_screenshots/`. A screenshot only proves a page rendered, so the
assertions carry the actual proof.

The OTP step is real, not stubbed. `otp_tokens.code_hash` is a bcrypt hash, so
the code cannot be read back out of the database — instead the test intercepts
the live `/auth/register` response to capture the issued code, then verifies
that code against the bcrypt hash PostgreSQL actually stored. If that assertion
passes, the OTP is provably the one the server will accept.

---

## Schema

Alembic owns the schema. A readable snapshot of the current DDL lives in
[`schema.sql`](schema.sql) — generated, never hand-edited.

Eight application tables (plus Alembic's `alembic_version`), all foreign-key linked:

```
users ──< items >── categories
           │  └──── locations          (a table, not a string column)
           ├──< claims >── users
           ├──< item_status_events     (append-only lifecycle audit)
           └──< notifications
users ──< otp_tokens
```

### Enum types

Four native PostgreSQL enum types, three of them modelling core domain concepts:

| Type           | Values                                       | Represents |
| -------------- | -------------------------------------------- | ---------- |
| `item_status`  | `reported` → `matched` → `claimed` → `closed` | Where an item is in its lifecycle. `closed` is terminal; transitions are enforced in `app/lifecycle.py`, and every move is appended to `item_status_events`. |
| `item_kind`    | `lost`, `found`                              | Whether the item was lost by someone or found by someone. Orthogonal to lifecycle — both kinds travel the same four states. This is what the original schema conflated into its status column. |
| `claim_status` | `pending`, `approved`, `rejected`            | The state of one person's claim on one item. Approving a claim is what drives the item to `claimed`; at most one claim per item may be `approved`. |
| `otp_purpose`  | `registration`, `password_reset`             | Which flow a one-time code belongs to, so a registration code cannot be replayed against a password reset. |

### Foreign keys

| Child | Column | Parent | On delete |
| ----- | ------ | ------ | --------- |
| `items` | `category_id` | `categories.id` | `SET NULL` |
| `items` | `location_id` | `locations.id` | `SET NULL` |
| `items` | `reporter_id` | `users.id` | `CASCADE` |
| `claims` | `item_id` | `items.id` | `CASCADE` |
| `claims` | `claimant_id` | `users.id` | `CASCADE` |
| `claims` | `decided_by_id` | `users.id` | `SET NULL` |
| `claims` | `superseded_by_id` | `claims.id` | `SET NULL` |
| `item_status_events` | `item_id` | `items.id` | `CASCADE` |
| `item_status_events` | `actor_id` | `users.id` | `SET NULL` |
| `notifications` | `user_id` / `item_id` | `users.id` / `items.id` | `CASCADE` |
| `otp_tokens` | `user_id` | `users.id` | `CASCADE` |

Deleting an item takes its claims, status history and notifications with it;
deleting a *category* or *location* leaves items intact with a null reference.
`claims` is further constrained by `UNIQUE (item_id, claimant_id)` — one claim
per person per item — and by the partial unique index
`uq_claims_one_approved_per_item` on `(item_id) WHERE status = 'approved'`.

### Search indexing, and the evidence for it

The search endpoint filters `items.name` and `items.description` with a
leading-wildcard `ILIKE`. **A btree index cannot serve that predicate**, so those
two columns carry `pg_trgm` GIN indexes instead:

```sql
CREATE INDEX ix_items_name_trgm        ON items USING gin (name gin_trgm_ops);
CREATE INDEX ix_items_description_trgm ON items USING gin (description gin_trgm_ops);
```

This was verified against **400,000 rows (70 MB heap)**, not assumed.

**A selective term uses both indexes via `BitmapOr` — 3.4 ms:**

```
EXPLAIN (ANALYZE) SELECT count(items.id) FROM items
WHERE items.name ILIKE '%01cfcd4f6b87%' OR items.description ILIKE '%01cfcd4f6b87%';

 Aggregate  (cost=3261.18..3261.19 rows=1) (actual time=3.291..3.292 rows=1)
   ->  Bitmap Heap Scan on items  (actual time=3.289..3.289 rows=1)
         Recheck Cond: ((name ~~* '%01cfcd4f6b87%') OR (description ~~* '%01cfcd4f6b87%'))
         ->  BitmapOr  (actual time=3.280..3.280)
               ->  Bitmap Index Scan on ix_items_name_trgm
               ->  Bitmap Index Scan on ix_items_description_trgm
 Execution Time: 3.391 ms
```

**The honest caveat — a non-selective term correctly ignores them:**

```
... WHERE items.name ILIKE '%headphones%' OR items.description ILIKE '%headphones%';

 Finalize Aggregate  (actual time=148.920..149.419 rows=1)
   ->  Parallel Seq Scan on items  (actual time=11.977..145.599 rows=12333 loops=3)
         Filter: ((name ~~* '%headphones%') OR (description ~~* '%headphones%'))
 Execution Time: 149.475 ms
```

That term matches ~9% of the table, and at that selectivity a parallel sequential
scan genuinely *is* cheaper — the planner is making the right call, not missing an
index. The same applies to small tables: at 30k rows the planner also preferred a
seq scan, and forcing `enable_seqscan=off` showed the index working and faster
(2.794 ms via `Bitmap Index Scan on ix_items_name_trgm`, versus 8.716 ms scanning).

So: these indexes pay off for the queries users actually type — a serial number,
a distinctive model name — and stay out of the way otherwise. They are not a
blanket speed-up for every possible search string.

The equality filters (`category_id`, `location_id`, `status`, `kind`,
`occurred_on`) have ordinary btree indexes, which *do* suit them, plus a
composite `(status, kind, occurred_on)` for the common "open found items, newest
first" listing.

### Regenerating `schema.sql`

After a real schema change (edit models → generate and apply a migration), refresh
the snapshot with the compose stack running:

```bash
./scripts/dump_schema.sh
```

---

## Migrations

Alembic is the source of truth for the schema. `Base.metadata.create_all()` is
not used to build a database anywhere — it survives only as the metadata that
autogenerate diffs against.

```bash
alembic current                              # what revision is this database at?
alembic history --verbose                    # the full history
alembic upgrade head                         # apply everything outstanding
alembic downgrade -1                         # step back one revision
```

After changing `app/db/models.py`:

```bash
alembic revision --autogenerate -m "describe the change"
# review the generated file, then:
alembic upgrade head
./scripts/dump_schema.sh                     # refresh the readable snapshot
```

**Always read the generated migration before applying it.** Autogenerate cannot
infer everything — the initial migration needed two hand-written additions, both
documented in its docstring: `CREATE EXTENSION pg_trgm` (required before the
`gin_trgm_ops` indexes), and explicit up-front enum creation, because
`item_status` is used by two tables and inline `sa.Enum` would try to
`CREATE TYPE` it twice.

`tests/test_migrations.py::test_no_pending_schema_changes` runs autogenerate
against the migrated database and fails if anything differs, so a model edit
without a matching migration breaks the build.

---

## Architecture

```
app/routers/       HTTP only — parse, delegate, serialise. Never touches the DB.
app/services/      Business rules, lifecycle enforcement, authorisation.
app/repositories/  All SQL lives here. The only layer that holds a Session.
app/db/            Engine, models, schema bootstrap.
app/schemas/       Pydantic request/response models.
app/dependencies.py  Composition root — builds services from a request session.
```

Routers depend on a *service*, never a session, so swapping the storage layer
means rewriting `app/repositories/` and nothing above it. This is enforced by
tests, not just convention — `tests/test_layering.py` parses the router modules
and fails the build if one imports SQLAlchemy, imports a repository, or calls
`db.*` directly.

---

## Tests

```bash
pytest                     # unit tests always run; integration tests need a DB
```

Integration tests look for `TEST_DATABASE_URL` (default
`postgresql://lostfound:lostfound@localhost:5432/lostfound`) and **skip** rather
than fail when no database is reachable, so the suite is green on a machine with
nothing installed.

With the compose stack running:

```bash
TEST_DATABASE_URL=postgresql://lostfound:lostfound@localhost:5432/lostfound pytest -q
# 161 passed
```

Extra checks:

```bash
python scripts/audit_routes.py             # every route has a typed body + response_model
python scripts/smoke_http.py http://localhost:8000   # black-box test of a running stack
```

CI runs lint, the route audit, and the full suite against a PostgreSQL service
container, then separately builds the compose stack and smoke-tests it over HTTP.

---

## Project history

This started as a Flask + MySQL server-rendered application. It was rebuilt as a
typed REST service: FastAPI replaced Flask, PostgreSQL replaced MySQL, the
`lost`/`found` status column plus `claimed` boolean became a real lifecycle enum
with a normalised `claims` table, and the single 459-line `app.py` was split into
router / service / repository layers. The schema was then put under Alembic
version control, replacing implicit `create_all()` at startup.
