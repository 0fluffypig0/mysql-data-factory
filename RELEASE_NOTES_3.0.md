# MySQL Data Factory 3.0.1 — Release Notes

## Version 3.0.1

Release Date: 2026-04-11

---

## What Changed in 3.0.1

### Bug Fix: Task Config Panel No Longer Disappears While Editing

Fixed a GUI interaction issue on the Tasks page.

Previous behavior:

- after selecting a task in the left task list
- when changing a combobox on the right-side config panel, such as sample method, PK mode, or execution mode
- the left-side task selection could be cleared by focus transfer
- the right-side config area would then disappear until the user clicked the table name again

Current behavior:

- the selected task remains selected while focus moves into the right-side configuration widgets
- the right-side configuration panel stays visible during combobox edits
- task editing now feels stable and continuous

Implementation note:

- `src/ui/page_tasks.py` now creates the task list with `exportselection=False`, which preserves the Listbox selection while the user interacts with widgets on the right

---

## Carry-Forward Capabilities from 3.0.0

The following remain unchanged from the initial 3.0 release:

- tkinter-based GUI
- embeddable Python offline runtime bundle
- `env_export/mysql_factory_env.zip` as the portable deployment artifact
- streamed chunk-file batch insertion for low memory usage
- bastion-host-friendly local runtime and append workflow

---

## Release Delivery Recommendation

For 3.0.1, the preferred way to hand the tool to downstream users is still:

1. source code
2. `env_export/mysql_factory_env.zip`

That keeps the target-machine workflow simple:

- unpack once
- configure `.env`
- run setup
- start using the tool

---

## Compatibility Notes

- Git tag for this release is `v3.0.1`
- user-facing release name is `3.0.1`
- the release is a small bugfix update on top of `v3.0.0`
