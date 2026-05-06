# GitHub Best Practices — Team Guide

A practical guide for collaborating on this repository. The goal is a clean,
reviewable history and a low-friction workflow for everyone on the team.

---

## 1. Branching

### 1.1 Branch types & naming

Use lowercase, hyphen-separated names with a `type/issue-id-short-description`
shape. The issue ID makes it trivial to trace a branch back to a ticket on the
GitHub board.

| Type        | When to use                                       | Example                                  |
| ----------- | ------------------------------------------------- | ---------------------------------------- |
| `feature/`  | New functionality                                 | `feature/issue-01-user-authentication`   |
| `fix/`      | Bug fixes (non-urgent)                            | `fix/issue-42-upload-timeout`            |
| `hotfix/`   | Urgent production fix                             | `hotfix/issue-58-login-crash`            |
| `chore/`    | Tooling, deps, build, configs (no behavior change) | `chore/issue-12-bump-fastapi`            |
| `refactor/` | Code restructuring without behavior change        | `refactor/issue-19-extract-graph-loader` |
| `docs/`     | Documentation-only changes                        | `docs/issue-07-add-api-readme`           |
| `test/`     | Adding or improving tests only                    | `test/issue-23-cover-auth-service`       |
| `spike/`    | Throwaway experiments / proofs of concept         | `spike/issue-30-langgraph-router`        |

**Rules of thumb**

- All lowercase, words separated by `-`.
- Always include the issue/ticket ID right after the type prefix.
- Keep the description short (3–5 words) but recognizable.
- Never commit directly to `main` — always branch.
- One branch = one issue. If scope grows, open a new issue and a new branch.
- Delete merged branches (locally and on the remote) to keep the branch list clean.

---

## 2. Commit messages

We follow [Conventional Commits](https://www.conventionalcommits.org/) — it
keeps history skimmable and enables automated changelogs.

### 2.1 Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

- **type** — one of: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`, `build`, `ci`, `revert`.
- **scope** *(optional)* — area of the codebase: `backend`, `frontend`, `api`, `auth`, `graph`, `ci`, etc.
- **subject** — imperative, lowercase, no trailing period, ≤ 72 characters.
  - Good: `add JWT refresh-token rotation`
  - Bad: `Added refresh tokens.`
- **body** *(optional)* — explain *why* the change was made, wrap at 72 chars.
- **footer** *(optional)* — issue references, breaking changes:
  - `Closes #14`, `Refs #22`
  - `BREAKING CHANGE: removes /v1/login endpoint`

### 2.2 Examples

```
feat(auth): add Google OAuth sign-in flow

Wires Firebase Auth Google provider into the mobile client and
exchanges the ID token with the backend for a session JWT.

Closes #18
```

```
fix(api): handle empty Firestore document on upload

Previously the upload endpoint returned 500 when the document
reference was created but the file write failed. Now it cleans
up the orphaned reference and returns 422.

Closes #42
```

```
chore(api): fix typos in OpenAPI metadata description
```

```
refactor(graph): extract knowledge-graph loader from router

No behavior change. Prepares for the per-domain loader work in #30.
```

### 2.3 Do / Don't

✅ Do
- Make commits **small and atomic** — one logical change per commit.
- Use the **imperative mood** (“add”, not “added” or “adds”).
- Reference the issue ID in the subject or footer.
- Run formatters/tests **before** committing.

❌ Don't
- `wip`, `fix`, `update`, `asdf`, `final final v2` as full messages.
- Mix unrelated changes in one commit (e.g. a feature + an unrelated dep bump).
- Commit generated files, secrets, `.env`, IDE config, or `.DS_Store`.
- Use `--no-verify` to skip hooks unless you have a real reason.

---

## 3. Pull Requests

### 3.1 Opening a PR

- Open against `main` (or `develop` if used).
- Title follows the same Conventional Commit format as commits:
  `feat(auth): add Google OAuth sign-in flow`
- Keep PRs **small** — aim for < ~400 lines changed. Split larger work.
- Mark as **Draft** while still in progress; mark **Ready for review** when done.

### 3.2 PR description template

```markdown
## Summary
What does this PR do, in 2–4 bullets?

## Why
Link to the issue and the user-facing motivation.

## Changes
- High-level list of changes.

## Testing
- How did you verify this? Steps, screenshots, or test output.

## Checklist
- [ ] Linked to issue (`Closes #N`)
- [ ] Tests added / updated
- [ ] Docs updated if behavior changed
- [ ] No secrets, generated files, or unrelated changes

Closes #N
```

### 3.3 Review etiquette

**As the author**

- Self-review the diff before requesting review — catch your own typos first.
- Respond to every comment (resolve, push a fix, or explain why not).
- Don't force-push after review starts; prefer fixup commits and squash on merge.

**As the reviewer**

- Aim to review within ~24 hours during the work week.
- Be kind, be specific, and suggest concrete changes.
- Distinguish blocking comments (`request changes`) from nits (prefix with `nit:`).
- Approve when it's good enough to ship — perfection is the enemy of progress.

### 3.4 Merging

- Prefer **Squash and merge** — one PR = one commit on `main`. Keeps history linear.
- Use **Rebase and merge** only when the per-commit history is genuinely useful.
- Avoid plain merge commits unless preserving merge topology is important.
- Delete the source branch after merging.

---

## 4. Keeping your branch up to date

Before opening a PR (and periodically while working on a long branch):

```bash
git fetch origin
git rebase origin/main          # preferred — keeps history linear
# or, if rebase is risky for the branch:
git merge origin/main
```

Resolve conflicts locally, run tests, then push. If you've already pushed and
rebased, use:

```bash
git push --force-with-lease     # safer than --force
```

`--force-with-lease` refuses the push if someone else has pushed in the
meantime, which protects their work.

---

## 5. What never goes into Git

- Secrets, API keys, tokens, `.env` files.
- Large binaries — use Git LFS or external storage.
- Editor/OS noise — `.DS_Store`, `.idea/`, `.vscode/` (unless intentionally shared).
- Generated artifacts — `node_modules/`, `dist/`, `build/`, `__pycache__/`.

Make sure `.gitignore` covers these. If a secret slips in, **rotate it
immediately** — removing it from history is not enough.

---

## 6. Quick reference

```bash
# Start new work
git checkout main
git pull
git checkout -b feature/issue-01-add-login

# Commit
git add <files>
git commit -m "feat(auth): add login screen"

# Sync with main
git fetch origin
git rebase origin/main

# Push and open PR
git push -u origin feature/issue-01-add-login

# After merge — clean up
git checkout main
git pull
git branch -d feature/issue-01-add-login
git push origin --delete feature/issue-01-add-login
```

---

## 7. TL;DR

1. Branch name: `type/issue-id-short-description` (e.g. `feature/issue-01-add-login`).
2. Commit message: `type(scope): imperative subject`, with a body when the *why* isn't obvious.
3. Small PRs, linked to an issue, with a clear description and a self-review.
4. Squash-merge into `main`, then delete the branch.
5. Never push secrets. Never force-push shared branches without `--force-with-lease`.
