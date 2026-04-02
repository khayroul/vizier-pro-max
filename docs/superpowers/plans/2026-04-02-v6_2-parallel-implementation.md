# Vizier v6.2 Parallel Implementation Plan

**Spec:** `docs/superpowers/specs/2026-04-02-v6_2-implementation-spec.md`  
**Packet registry:** `config/bootstrap/parallel_work_packets.yaml`  
**Automation helper:** `python3 -m scripts.bootstrap.parallel_sessions`

---

## 1. Goal

This plan exists so multiple sessions can implement the v6.2 architecture in parallel without colliding on files or inventing incompatible contracts.

The workflow is:

1. land the serial contracts packet
2. prepare packet-specific worktrees automatically
3. run parallel implementation sessions inside those worktrees
4. merge in dependency order
5. only begin clone and CI packets after the foundations stabilize

---

## 2. Packet Summary

| Packet | Wave | Purpose |
|---|---|---|
| `contracts-ledger` | `wave0` | Freeze shared contracts and state layout |
| `bridge-capture` | `wave1` | Capture external and runtime events as evidence |
| `observational-memory` | `wave1` | Build canonical observation and reflection storage |
| `selfbuild-gate` | `wave1` | Add replay and benchmark-based promotion decisions |
| `openspace-candidate-flow` | `wave1` | Refactor OpenSpace to candidate-only outputs |
| `distillation-governance` | `wave1` | Limit distillation to approved traces and gated deployment |
| `quality-ci` | `wave2` | Harden CI and first-party quality routing |
| `clone-designspec` | `wave2` | Rebuild clone flow around `DesignSpec` and benchmarks |

---

## 3. Dependency Rules

### 3.1 Serial gate

`contracts-ledger` must land first.

No other packet should define its own copy of the core contracts. If another session starts before Wave 0 lands, it must treat the contracts packet as read-only input and be ready to rebase.

### 3.2 Parallel wave

After `contracts-ledger` lands, the Wave 1 packets can run in parallel because their write sets are intentionally disjoint.

### 3.3 Later wave

`quality-ci` and `clone-designspec` wait until the foundation packets are stable enough to avoid churn.

---

## 4. Automatic Usage

The helper script is the default workflow. Use it instead of manually inventing branches or worktree layouts.

### 4.1 Inspect the program

```bash
cd /Users/Executor/vizier-pro-max
python3 -m scripts.bootstrap.parallel_sessions list
python3 -m scripts.bootstrap.parallel_sessions show contracts-ledger
```

### 4.2 Prepare packet worktrees

Prepare a single packet:

```bash
python3 -m scripts.bootstrap.parallel_sessions prepare contracts-ledger
```

Prepare a full wave:

```bash
python3 -m scripts.bootstrap.parallel_sessions prepare --wave wave1
```

Dry run first if you want to preview branches and paths:

```bash
python3 -m scripts.bootstrap.parallel_sessions prepare --wave wave1 --dry-run
```

### 4.3 What the helper creates

For each prepared packet, the helper creates:

- a dedicated worktree under `.worktrees/v6_2/<packet-slug>/`
- a dedicated branch using the `codex/v6-2-*` prefix
- a local ignore entry for `.codex-session/`
- `.codex-session/WORK_ORDER.md`
- `.codex-session/PROMPT.txt`
- `.codex-session/packet.json`

Those generated files are local-only and should not be committed.

### 4.4 Start a coding session

Open the prepared worktree in a new session and use the generated prompt:

```bash
cd /Users/Executor/vizier-pro-max/.worktrees/v6_2/contracts-ledger
cat .codex-session/PROMPT.txt
```

The session should treat `.codex-session/WORK_ORDER.md` as the packet contract for that worktree.

### 4.5 Check status

```bash
python3 -m scripts.bootstrap.parallel_sessions status
```

This shows:

- which packets have prepared worktrees
- branch names
- whether the worktree is dirty
- whether the session files are present

---

## 5. Manual Fallback

If the helper is unavailable, manual setup must follow the same rules:

1. create one branch per packet
2. create one worktree per packet
3. only edit the packet's owned paths
4. do not change another packet's files unless the master branch already absorbed a dependency
5. keep local session instructions out of tracked files

Manual commands should mirror the helper's defaults:

```bash
git worktree add -b codex/v6-2-contracts-ledger .worktrees/v6_2/contracts-ledger master
```

---

## 6. Session Segregation Rules

Every packet session must obey these rules:

- edit only the packet's owned paths
- read shared inputs freely, but do not patch them unless they are in your owned paths
- do not move files into another packet's ownership to make your packet easier
- do not add convenience edits in unrelated files while "already here"
- if a dependency is missing, stub against the contract or pause for merge instead of freelancing new interfaces

### 6.1 Allowed behavior

- reading spec and packet registry files
- importing shared contract modules
- adding tests for the packet's owned files
- adding new files inside the packet's owned directory scope

### 6.2 Disallowed behavior

- modifying another packet's tests
- changing `pyproject.toml` unless you are on `quality-ci`
- changing `pipelines/clone_converge.py` unless you are on `clone-designspec`
- changing `bridge/*` unless you are on `bridge-capture`
- changing `augments/selfbuild/*` unless you are on `selfbuild-gate`

---

## 7. Merge Protocol

### 7.1 Recommended order

1. merge `contracts-ledger`
2. rebase or recreate Wave 1 worktrees on the new master
3. merge Wave 1 packets in any order that respects their direct dependencies
4. merge `quality-ci`
5. merge `clone-designspec`

### 7.2 Before merging any packet

Run the packet's verification commands from `config/bootstrap/parallel_work_packets.yaml`.

If a packet introduces new command surfaces or contract meanings, update the relevant docs before merge.

### 7.3 After merging a dependency

Refresh outstanding packet worktrees:

```bash
git -C /Users/Executor/vizier-pro-max fetch origin
git -C /Users/Executor/vizier-pro-max/.worktrees/v6_2/<packet> rebase origin/master
```

If rebase churn is excessive, archive the packet worktree, re-run `prepare`, and replay the packet against the new base.

---

## 8. Operating Checklist

Use this checklist every time you spin up parallel implementation sessions.

1. Run `python3 -m scripts.bootstrap.parallel_sessions list`.
2. Run `show` on the packet you want.
3. Prepare the packet or wave with `prepare`.
4. Open the generated worktree.
5. Read `.codex-session/WORK_ORDER.md`.
6. Implement only the owned paths.
7. Run the packet verification commands.
8. Merge in dependency order.
9. Run `status` again to see what remains active.

---

## 9. If You Forget How To Operate It

Use this sequence:

```bash
cd /Users/Executor/vizier-pro-max
python3 -m scripts.bootstrap.parallel_sessions list
python3 -m scripts.bootstrap.parallel_sessions show contracts-ledger
python3 -m scripts.bootstrap.parallel_sessions prepare contracts-ledger
python3 -m scripts.bootstrap.parallel_sessions status
```

Then go into the prepared worktree and read:

```bash
cat /Users/Executor/vizier-pro-max/.worktrees/v6_2/contracts-ledger/.codex-session/WORK_ORDER.md
```

If you do only that, you will still be operating the parallel program correctly.
