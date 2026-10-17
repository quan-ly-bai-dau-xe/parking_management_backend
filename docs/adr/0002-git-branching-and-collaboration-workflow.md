# ADR-0002: Git Branching Strategy and Collaboration Workflow

- **Status**: Proposed - pending Owner approval
- **Date**: 2026-10-11
- **Deciders**: Owner, Tech Lead, Engineering Team
- **Technical Context**: Git Version Control, Public Repo Collaboration & PR Workflow

## 1. Context & Conflict Resolution

The project onboarding revealed a conflict between:

1. **Team Charter (`04. [BM] Team Charter.docx`)**: Branches split only from `dev`; PRs target `dev`; >= 1 peer approval + `Approved` label; merge commit (`--no-ff`).
2. **`git-organization.xlsx`**: Illustrated PRs directly into `main` with Leader review.
**Resolution**: Adopt Team Charter Git Flow for enterprise stability on the public repository.

## 2. Decision Outcome

### 2.1. Branch Hierarchy & Integration

- **`main` (Protected Release)**: Production-ready code. Merged exclusively from `dev` by Tech Lead.
- **`dev` (Protected Integration)**: Active sprint integration. All work branches split from `dev`. PRs target `dev`.
- **Merge Strategy**: PRs merged into `dev` via **Merge Commit** (`--no-ff`). Rebase/squash disabled to retain provenance.

### 2.2. Branch Taxonomy & Commit Standard

- **Branch Naming**:
  - `feature/<issue-id>-<short-description>`
  - `bugfix/<issue-id>-<short-description>`
  - `hotfix/<issue-id>-<short-description>` (from `main` only for critical production fixes).
- **Conventional Commits v1.0.0**: English, imperative mood:
  - Format: `<type>(<scope>): <subject>` (e.g. `feat(ticket): add soft delete endpoint`, `fix(auth): enforce argon2`).

### 2.3. PR Requirements & DoD Gates

1. Minimum 01 peer review approval.
2. Complete safe-delete checklist in `.github/PULL_REQUEST_TEMPLATE.md`.
3. DoD verification: 100% test pass, coverage >= 80%, clean `ruff`, `mypy`, and `makemigrations --check`.

### 2.4. AI Agent Git Governance

- AI agents are strictly forbidden from executing git write operations (`add`, `commit`, `push`, `merge`, `rebase`, `tag`, branch changes) without explicit Owner approval.
- Permissions `ask` in `.claude/settings.json` serve as a local safety net; true protection is enforced by GitHub branch protection and human reviews. Read-only git commands are unrestricted.

## 3. Consequences

- **Positive**: Clean separation between development and releases, complete audit trail, zero accidental commits.
- **Negative**: Requires maintaining two long-lived branches (`main` and `dev`).

## 4. References

- Conventional Commits: <https://www.conventionalcommits.org/en/v1.0.0/>
- GitHub Protected Branches: <https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches>
