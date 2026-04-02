# Hermes Submodule Setup

Vizier treats the pinned `hermes-agent` submodule commit as the source of
truth for runtime compatibility.

## Recommended local setup

```bash
git submodule update --init --recursive
git -C hermes-agent remote set-url origin git@github.com:khayroul/hermes-agent.git
git -C hermes-agent remote add upstream git@github.com:NousResearch/hermes-agent.git
python3 -m scripts.bootstrap.doctor
```

## Maintenance workflow

- `origin` is the writable fork used for Vizier-specific patches.
- `upstream` is the canonical Hermes repository used for intentional syncs.
- The superproject-pinned submodule SHA is the runtime truth.
- The `vizier-gate2-patch` branch is the preferred maintenance branch when
  doing Hermes patch work, but detached HEAD at the pinned commit is also
  acceptable.

## Update flow

```bash
git -C hermes-agent fetch upstream
git -C hermes-agent checkout vizier-gate2-patch
git -C hermes-agent merge upstream/main
# run Vizier checks here
git add hermes-agent
git commit -m "chore: bump hermes-agent submodule"
```
