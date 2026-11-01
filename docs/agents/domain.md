# Domain docs

This repository is single-context. Domain documentation is rooted at the
repository root.

## Before exploring

- Read `GLOSSARY.md` when it exists.
- Read relevant decisions in `docs/ADR/` before changing behavior covered by
  an ADR.

If these files do not exist, proceed without flagging their absence or creating
them proactively.

## Layout

```text
/
├── GLOSSARY.md
├── docs/ADR/
└── src/
```

## Vocabulary and decisions

Use glossary terms in issue titles, proposals, and tests. If a needed concept
is not defined, note the gap for domain modeling instead of inventing
competing terminology.

If a change conflicts with an existing ADR, call out the conflict explicitly
rather than silently overriding it.
