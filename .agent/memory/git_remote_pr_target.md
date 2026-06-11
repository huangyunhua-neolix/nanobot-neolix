---
name: Git remote / PR target for nanobot-neolix
description: Iron rule — all PRs go to huangyunhua-neolix/nanobot-neolix; that URL IS the upstream, not a personal fork
type: feedback
---

For the nanobot-neolix project, the upstream / "本仓库" is `git@github.com:huangyunhua-neolix/nanobot-neolix.git`. Despite the user-style account name (`huangyunhua-neolix/`), this is THE project repo — not a personal fork. All PRs MUST target this repo. Never push to HKUDS/nanobot or any other mirror, and never create a separate fork.

**Why:** Got burned on 2026-06-11 — I pushed to `origin` and reported the GitHub-provided "create PR" URL, then second-guessed myself and asked the user whether it should go to HKUDS/nanobot or "some internal org". The user was annoyed because (a) `origin` was already the correct repo, (b) I treated the user-style name as evidence of a fork when it isn't, and (c) the rule was undocumented.

**How to apply:**
- Default `origin` for this repo points to the correct target. Verify with `git remote -v` before any push.
- If `origin` ever shows a different URL, STOP and ask before pushing — do NOT silently re-derive the upstream.
- Iron rule is now codified in `AGENTS.md` under "## Contribution Flow → Git remote / PR target".
- PR/MR links: always raw URLs (`https://github.com/.../pull/123`), never `[text](url)` markdown — the merge tooling can't parse markdown links.
