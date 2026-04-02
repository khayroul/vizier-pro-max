# Vizier v6.2 Prompt Pack

Use these prompts for the parallel implementation program defined in:

- `docs/superpowers/specs/2026-04-02-v6_2-implementation-spec.md`
- `docs/superpowers/plans/2026-04-02-v6_2-parallel-implementation.md`
- `config/bootstrap/parallel_work_packets.yaml`

## Prompt Files

- `docs/superpowers/prompts/2026-04-02-v6_2-master-coordinator.md`
- `docs/superpowers/prompts/2026-04-02-v6_2-packet-worker.md`
- `docs/superpowers/prompts/2026-04-02-v6_2-reviewer-integrator.md`
- `docs/superpowers/prompts/2026-04-02-v6_2-merger-refresh.md`

## Usage Order

1. Start the **master coordinator** first.
2. The master inspects packet state and prepares the next worktree using `python3 -m scripts.bootstrap.parallel_sessions`.
3. Start one or more **packet worker** sessions inside the prepared worktrees.
4. When a worker finishes, start a **reviewer/integrator** session on that packet branch or worktree.
5. If approved, start the **merger/refresh** session to merge the packet and refresh downstream worktrees.
6. Return to the **master coordinator** to choose the next packet or next wave.

## Default Execution Sequence

1. `contracts-ledger`
2. Wave 1 in parallel:
   - `bridge-capture`
   - `observational-memory`
   - `selfbuild-gate`
   - `openspace-candidate-flow`
   - `distillation-governance`
3. `quality-ci`
4. `clone-designspec`

## If You Forgot Everything

Run:

```bash
cd /Users/Executor/vizier-pro-max
python3 -m scripts.bootstrap.parallel_sessions list
python3 -m scripts.bootstrap.parallel_sessions show contracts-ledger
python3 -m scripts.bootstrap.parallel_sessions prepare contracts-ledger
```

Then use:

- the master prompt to coordinate
- the worker prompt in the prepared worktree

That is enough to restart the program correctly.
