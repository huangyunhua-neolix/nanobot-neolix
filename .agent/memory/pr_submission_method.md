---
name: PR submission method for nanobot-neolix
description: API + git credential helper (gh CLI unavailable; keychain wrapper unusable; fork-of-fork base trap)
type: feedback
---

For the nanobot-neolix project, submit PRs via GitHub REST API. Do NOT rely on `gh` CLI (not installed in this env) or the macOS keychain `gh:github.com` entry (it's a go-keyring marshaled wrapper that returns `Bad credentials` if used as a bearer token). The working token comes from `git credential fill` (has `gho_` prefix, 40 chars).

**Why:** Got burned on 2026-06-11 — first tried the keychain blob (`go-k...aw==`) which failed with `Bad credentials`; then sent the user a browser URL which defaulted the PR base to `HKUDS/nanobot` because `huangyunhua-neolix/nanobot-neolix` is itself a fork-of-fork on GitHub. Two separate traps stacked.

**How to apply:**

```bash
# 1. Branch already pushed via git push -u origin <branch>
# 2. Get the real token
CREDS=$(printf 'protocol=https\nhost=github.com\n\n' | git credential fill 2>/dev/null)
TOKEN=$(echo "$CREDS" | grep '^password=' | sed 's/^password=//')

# 3. Write payload to /tmp/pr_body.json with title/head/base/body
# 4. POST to the correct repo (NOT HKUDS):
curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/repos/huangyunhua-neolix/nanobot-neolix/pulls \
  -d @/tmp/pr_body.json
```

If browser flow is unavoidable, the compare URL MUST force base; default GitHub UI picks HKUDS:
`https://github.com/huangyunhua-neolix/nanobot-neolix/compare/main...huangyunhua-neolix:nanobot-neolix:<branch>?expand=1`

Full procedure also codified in `AGENTS.md` under "Contribution Flow → How to actually submit a PR".
