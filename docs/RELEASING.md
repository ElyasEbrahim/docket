# Releasing pgdocket

> **Not in use (decision 2026-10-23).** pgdocket is installed from GitHub (`pip install "git+https://github.com/ElyasEbrahim/pgdocket"`) until people use it. Don't push `v*` tags: the release workflow would try to publish to PyPI, which isn't set up. This page documents how to publish when that changes.

A release publishes three things from one version tag:

| Where | What |
| --- | --- |
| PyPI | `pip install pgdocket` (wheel + sdist) |
| GitHub Container Registry | `docker pull ghcr.io/elyasebrahim/pgdocket:<version>` |
| GitHub Releases | the same files, with a link to the changelog |

The workflow is [.github/workflows/release.yml](../.github/workflows/release.yml). It runs only when a tag `v*` is pushed, and refuses to run if the tag doesn't match `pgdocket/__init__.py`.

## One-time setup (the maintainer, on PyPI)

PyPI uses *trusted publishing*: GitHub proves the release came from this repository's workflow, so no PyPI token is stored anywhere.

1. Sign in at [pypi.org](https://pypi.org) (create an account if needed, with two-factor authentication).
2. Go to **Your account → Publishing → Add a new pending publisher** and enter:
   - PyPI project name: `pgdocket`
   - Owner: `ElyasEbrahim`
   - Repository: `pgdocket`
   - Workflow: `release.yml`
   - Environment: `pypi`
3. In the GitHub repository, **Settings → Environments → New environment → `pypi`**. Optionally add yourself as a required reviewer, so every PyPI upload waits for your click.

The container registry and GitHub release need no setup; they use the workflow's own token.

## Each release

1. Make sure CI is green on `master` and `CHANGELOG.md` has an entry for the version.
2. Set the version in `pgdocket/__init__.py` (e.g. `0.1.0a1`, `0.1.0a2`, `0.1.0`), commit, push.
3. Tag and push the tag:
   ```bash
   git tag v0.1.0a1
   git push origin v0.1.0a1
   ```
4. Watch the **Release** workflow. Versions with `a`, `b` or `rc` are marked as pre-releases.

## Before PyPI is set up

Anyone can already install straight from GitHub:

```bash
pip install "git+https://github.com/ElyasEbrahim/pgdocket"
```

or build the image locally with `docker build -t pgdocket .`.
