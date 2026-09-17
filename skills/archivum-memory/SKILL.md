---
name: archivum-memory
description: Use when working in any repository on a machine linked to Archivum - before debugging an error, before changing unfamiliar code, and after finishing a piece of work. Archivum remembers what broke before, what fixed it, and why the code is the way it is. If this repository is not indexed yet, indexing it is the first thing to do, not a reason to skip this skill.
---

# Archivum memory

Archivum is memory that remembers your code and the work you did on it: the
graph of a repository, the sessions that changed it, and the fixes that settled
past bugs. This skill is about *consulting* that before you act, so you are not
solving something you already solved.

## First, is this repository indexed?

`list_repositories` answers it. If this repository is not there, index it before
anything else — from the correct side of the wire.

**The repository is on the machine you are working on.** This is the normal
case, and it is a shell command rather than a tool, because the server cannot
read this machine's disk:

```
archivum index
```

**The repository lives on the server itself.** Only then can the tool do it:

```
index_repository(path="<absolute path on the server>")
```

Calling `index_repository` with a path on your own machine fails with `'...' is
not a directory on this server`. That is not a typo to hunt for — it means the
call was made from the wrong side. Use `archivum index`.

An unindexed repository is the normal state of a machine that was linked
recently. It is a reason to run one command, not a reason to stop reading —
`recall_fix` and `record_work` work regardless, and every later question in this
skill gets better answers once the code graph exists.

## The rule

**Ask before you dig. Record what you learned.**

Two of these are cheap and one is free — the cost of skipping them is redoing
work you already did months ago and forgot.

## When you hit an error

Before reading any code, before forming a theory:

```
recall_fix(symptom="<paste the error>")
```

If it comes back with something, you have the symptom, the diagnosis, the files
that changed, and how it was verified — cited back to the session it came from.
Read that before you start. It is often the whole answer.

If it comes back empty it says so. That is also useful: this is new trouble, and
worth recording once you solve it.

## When you touch unfamiliar code

```
retrieve_code_context(query="<what you are looking for>", repo="<repo name>")
```

Returns the symbols that matter with their signatures, summaries and
`file:line` citations. Ask for `include_source=true` when you need the bodies
rather than the map — leave it off when you are orienting, because the source of
everything is a lot of context to spend on a question you have not asked yet.

Follow the graph from there: `graph_neighbors` for what a symbol connects to,
`graph_shortest_path` for how two things relate.

## When you finish

`record_work` is how work gets remembered. Session capture, where it is running,
infers what happened from a transcript; this is you stating it. When a piece of
work mattered — a non-obvious bug, a decision with a reason, a gotcha worth
warning the next person about — say so plainly:

```
record_work(
  request="what was asked",
  outcome="what you found and did, including the cause",
  changed_paths=["..."],
  verified_by="the command that proves it",
)
```

Be specific about the *cause*. "Fixed the test" is worth nothing in six months.
"The fixture shared a connection across event loops, so the second test saw a
closed socket" is worth a great deal.

## What not to do

- **Do not paste secrets into `record_work`.** It is memory, and memory is read
  back. Transcripts are redacted on capture; what you type here is not.
- **Do not record work you did not do.** A fix that was not verified should say
  so rather than claiming a test that never ran. Archivum tracks whether a fix
  was verified and weights it accordingly; a false claim poisons that.
- **Do not skip `recall_fix` because the error looks simple.** Simple-looking
  errors are exactly the ones that recur.

## If Archivum is not reachable

Say so and carry on. Memory is an advantage, not a dependency — a vault you
cannot reach should slow you down, not stop you.
