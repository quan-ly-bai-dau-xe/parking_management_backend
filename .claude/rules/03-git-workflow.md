# 03-git-workflow.md — Git Collaboration & Branching Standards

## 1. Branch Strategy (Resolved via ADR-0002)

- **`main`**: Protected production-ready release branch. Only merged from `dev` by the Team Lead. Direct commits and pushes are strictly blocked.
- **`dev`**: Protected shared integration branch. Base branch for all feature, bugfix, and chore development.
- **Feature Branches**: Split strictly from `dev`:
  - `feature/<issue-id>-<short-description>`: New functional features.
  - `bugfix/<issue-id>-<short-description>`: Defect fixes.
  - `hotfix/<issue-id>-<short-description>`: Critical production fixes split from `main`.

## 2. Pull Request & Merge Policy

- Target branch for all development PRs is `dev`.
- Every PR requires at least 01 peer approval and passing CI checks prior to merging.
- Merges into `dev` must generate a merge commit (`--no-ff` equivalent) to preserve commit history.
- Pull request description must follow `.github/PULL_REQUEST_TEMPLATE.md` and complete the Safe Delete & Destructive Operations checklist.

## 3. Commit Message Conventions

- **Language**: English only, imperative mood.
- **Format**: Conventional Commits specification:

  ```text
  <type>(<scope>): <subject>

  [optional body explaining WHY, not WHAT]
  [optional footer: Closes #123]
  ```

- **Allowed Types**: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`.
- **Examples**:
  - `feat(ticket): implement soft delete endpoint with expiration check`
  - `fix(auth): enforce Argon2 password validation matching SRS 4.3.3`
  - `test(employee): add concurrency test with select_for_update`

## 4. AI Agent Operational Constraints (Owner Mandate)

- AI agents are STRICTLY FORBIDDEN from running any git write operations (`add`, `commit`, `push`, `merge`, `rebase`, `tag`, branch changes, `reset`) without explicit approval from the Owner in the current conversation session.
- Never automatically merge or push.
- Git read-only operations (`status`, `diff`, `log`, `show`, `ls-files`, `check-ignore`, `add -n`) are always permitted; write operations are only allowed when explicitly approved by the Owner.
