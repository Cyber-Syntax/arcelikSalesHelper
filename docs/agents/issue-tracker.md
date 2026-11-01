# Issue tracker: Hybrid local + GitHub

This repository uses a hybrid workflow:

- Small, well-understood tasks are tracked as checklist items in `docs/todo.md`.
- Large tasks, bugs needing detailed reproduction or error information, and work requiring discussion are tracked as GitHub Issues in `Cyber-Syntax/arcelikSalesHelper`.

## Choosing the tracker

Use `docs/todo.md` when work is small, self-contained, and can be completed without a discussion thread. Preserve its checklist structure and update the item when complete.

Use GitHub Issues when work is complex, user-facing, blocked, requires investigation, needs detailed logs or reproduction steps, or benefits from comments and status history. Use the `gh` CLI from this clone.

## GitHub conventions

- Create: `gh issue create --title "..." --body "..."`
- Read: `gh issue view <number> --json number,title,body,labels,comments`
- List: `gh issue list --state open`
- Comment: `gh issue comment <number> --body "..."`
- Close: explain the resolution with a comment, then run `gh issue close <number>`.

Pull requests are not a request surface for triage.
