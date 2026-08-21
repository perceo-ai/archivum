# Daily Use

What the vault is like to live in, as opposed to what it can store.

## The stream

Home is a reverse-chronological feed of everything that happened, with the
capture box at the top. Seven kinds appear:

| Kind | From |
|---|---|
| `page_created`, `page_edited` | Writes to the vault, yours or an agent's |
| `suggestion` | Memory waiting on your review, decided in place |
| `ingest` | Files and URLs you brought in |
| `memory` | Assets distillation produced |
| `session` | A captured agent session, labelled by what kind of work it was |
| `fix` | A remembered repair: what broke, what caused it, whether it was checked |

Sessions and fixes were the gap. Capture runs automatically, and capture you
cannot see is hard to tell apart from no capture at all.

## Tasks

A task is a checkbox line in a page — `- [ ] Ship it` — not a row in a table.
There used to be a `life_tasks` table; it was deleted because the tool wrote to
a store no screen read, so there were two models of the same noun and only one
was visible.

Open tasks ride along with the first page of the stream as a standing list above
the timeline. Ticking one rewrites the line in the file and reindexes, which is
what keeps a task the same object whether you ticked it in Archivum or in your
own editor. Generated pages under `code/`, `memory/` and `skills/` are skipped:
a todo list is something you keep, not something the code graph writes for you.

## Finding things

The search box on **Everything** runs the hybrid endpoint — semantic, keyword and
bounded graph — debounced, keeping the engine's ranking. It used to filter titles
in the browser, which meant anything you could not name by title was effectively
lost while the embeddings sat unused. A failed search falls back to title
matching rather than showing nothing.

⌘K is **Ask**: cited answers over the vault. Different gesture, different job.

## Today

`T`, or the Today button, opens the daily note and creates it on first ask. The
endpoint existed from the beginning and nothing called it, so there was no
"today" — the one page a daily-notes habit needs to be one keystroke away.

## Keyboard

| Key | Does |
|---|---|
| `C` | Capture a thought from anywhere |
| `T` | Today's note |
| `S` / `E` / `V` | Stream, Everything, Visualized |
| `⌘K` | Ask |
| `⌘P` | Jump to a page |
