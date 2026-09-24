# Ticket 008: Restore installable governance runtime

- **ID**: ticket-008
- **Owner**: agent:codex
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION

SESSION_EXECUTION_AUTHORIZATION: user requests continued systemic improvements,
merge and testing. This disjoint dependency preserves PLF-003, tests PR7 and
Taskand PR51. The existing tests CI tries unavailable wellman==0.20.43.
Adopt the already published 0.20.50 standard through its pinned generator.
No protected approval, application installation or production changes.

- [x] AC-01: Published immutable adoption and clean runtime installation succeed.
- [x] AC-02: CI-equivalent gates and existing local regressions pass.
- [ ] AC-03: Push reviewable recovery and request protected publication; distinguish
  configuration blockers from test results and actual merge.

Session bound: 120 minutes. Branch/worktree are allocated by project/new-ticket.sh.
Other tickets and worktrees retain their owner and source unchanged.

Pre-commit plan correction: the six-file immutable adoption is class M (class S
allows five files). The original six-file scope and budgets remain unchanged.
Released the earlier lease before rebinding the corrected intent.

Validation: clean venv installed wellman 0.20.50 from the published upstream
runtime tag; installed CLI and managed gate pass. Generator check is current.
Existing PR7 local suite passes 22/22; Taskand admission regressions pass 13/13.
Standard-pack mode remains audit with eight missing baseline declarations;
this update respects that existing mode and does not claim full pack adoption.
Protected publication still needs the tests profile and an installed App.
