---
title: 'Branch or not to branch: git for analytics engineers in one picture'
date: 2026-11-20
published_at: '2026-11-20T13:04:35Z'
slug: git-for-analytics-engineers
description: What branch, main, origin and origin/main really are, why git status
  can lie, and when to fetch, pull or rebase. One picture, one daily routine.
tags:
- dbt
read_time: 12
status: published
---

I keep seeing the same git setup on data teams: five commands copied from a wiki page in someone's first week, and a small prayer whenever one of them prints red text.

It holds up until the morning `git status` says your branch is up to date and your pull request still collides with work you have never seen. Both statements were true at the same time. Once you see why, most of git stops being scary.

<div class="post-brief">
<ul>
<li><code>git status</code> reports on a snapshot that can be days old.</li>
<li>Most git panic traces back to four words nobody explained.</li>
<li>One picture and one real metric change cover a normal working day.</li>
</ul>
</div>

<div class="callout callout-info">
<span class="callout-label">the example</span>
<p>Telhado is fictional: a rooftop-solar co-op in Porto with a small dbt project. I ran every git command in this post on git 2.54 in a scratch repository, with two clones playing two teammates, including the rebase conflict and the squash merge. The outputs are copied from those runs.</p>
</div>

---

## Your code lives in four places

Picture a restaurant that keeps its recipes in one binder on the kitchen shelf. Every cook follows that binder. You take a full photocopy home, scribble changes on sticky notes, and bring them back for the head chef to approve. Before leaving the kitchen you snapped a photo of the shelf, so you know what the binder looked like.

The photo is the part everyone forgets. Git works the same way:

<figure>
<picture>
<source media="(max-width: 600px)" srcset="../assets/posts/git-for-analytics-engineers/four-places-mobile.svg">
<img src="../assets/posts/git-for-analytics-engineers/four-places.svg" alt="Two dashed areas, your laptop and GitHub. On the laptop: a working folder, local branches main and fix/generation-timezone, and an origin/main snapshot box. On GitHub: origin with main and the same branch. Arrows show commit from the folder to local branches, push from local branches to origin, fetch from origin to the snapshot, and pull, rebase or merge from the snapshot into local branches.">
</picture>
<figcaption>Only fetch, pull and push cross the line between your laptop and GitHub. Everything else happens locally.</figcaption>
</figure>

<div class="ts-block">
<div class="ts-row">
  <span class="ts-label">commit</span>
  <span class="ts-desc">A saved snapshot of the project with a message and an ID (a hash like <code>dec1e17</code>).</span>
</div>
<div class="ts-row">
  <span class="ts-label">branch</span>
  <span class="ts-desc">A movable label that points at one commit. New commits move the label forward.</span>
</div>
<div class="ts-row">
  <span class="ts-label">main</span>
  <span class="ts-desc">The branch everyone treats as the truth, and the one production usually builds from. It's only a name: GitHub has used it for new repositories since October 2020, and older ones may say <code>master</code>.</span>
</div>
<div class="ts-row">
  <span class="ts-label">origin</span>
  <span class="ts-desc">The default nickname for the repository you cloned from. For most teams, the one on GitHub.</span>
</div>
<div class="ts-row">
  <span class="ts-label">origin/main</span>
  <span class="ts-desc">Your laptop's copy of where <code>main</code> was on origin the last time you talked to it. The photo of the shelf.</span>
</div>
<div class="ts-row">
  <span class="ts-label">HEAD</span>
  <span class="ts-desc">Where you are right now: the branch your next commit will land on.</span>
</div>
</div>

Here is the morning from the opening. My teammate Ana merged two commits into `main` on GitHub. On my laptop, nothing had talked to GitHub since. I asked git where I stood:

```bash
$ git status
On branch main
Your branch is up to date with 'origin/main'.
```

Up to date with the photo. Then I ran `git fetch`, which downloads new commits and moves `origin/main`, without touching my files or my branches:

```bash
$ git fetch
   323b105..54742cf  main       -> origin/main
$ git status
On branch main
Your branch is behind 'origin/main' by 2 commits, and can be fast-forwarded.
```

<div class="pull-quote">
<code>git status</code> compares you with a photo, not with GitHub. <code>git fetch</code> takes a new photo.
</div>

<img src="../assets/posts/git-for-analytics-engineers/status-before-after.png" alt="Two terminal panes side by side. The left pane, before fetch, shows git status saying the branch is up to date with origin/main. The right pane runs git fetch, which moves origin/main from 323b105 to 54742cf, then git status says the branch is behind origin/main by 2 commits.">

---

## Branch or not to branch

Branch. In a team repository, every change starts on its own branch and reaches `main` through a pull request, even a one-line fix. `main` is what your production job builds from, so writing on it directly is writing in the shared binder in pen.

Branches are cheap enough that there's no reason to skip them. In my scratch repository a branch was a 41-byte file: one commit hash and a newline. Creating one copies nothing.

<div class="decision-tree">
<p class="decision-tree-title">New branch or not?</p>
<div class="decision-step">
  <span class="decision-q">Starting any change to models, tests or macros in a team repo</span>
  <span class="decision-a">New branch from a freshly pulled <strong>main</strong></span>
</div>
<div class="decision-step">
  <span class="decision-q">A reviewer asked for a fix on your open pull request</span>
  <span class="decision-a">Commit on the <strong>same branch</strong>; the PR updates itself</span>
</div>
<div class="decision-step">
  <span class="decision-q">Two unrelated changes</span>
  <span class="decision-a"><strong>Two branches</strong>, two pull requests, two easy reviews</span>
</div>
<div class="decision-step">
  <span class="decision-q">A personal sandbox nothing deploys from</span>
  <span class="decision-a">Committing to <strong>main</strong> is fine</span>
</div>
</div>

My rule: a branch lives for days, not weeks. The longer it lives, the further `main` moves away from it, and every day adds to the conflict you resolve at the end. Name it after the change (`fix/generation-timezone`), not after yourself.

---

## Fetch, pull, rebase: what each one changes

Back to Telhado. I'm on `fix/generation-timezone` with one commit that converts timestamps to Lisbon time. Meanwhile Ana's two commits (`dim_sites` and its tests) are now on `main`. My branch has fallen behind, and four commands could deal with that:

<div class="tradeoff-grid">
<div class="tradeoff-row header">
  <span class="tradeoff-cell">Command</span>
  <span class="tradeoff-cell">What it does</span>
  <span class="tradeoff-cell">Changes your files?</span>
  <span class="tradeoff-cell">Use it when</span>
</div>
<div class="tradeoff-row">
  <span class="tradeoff-cell"><code>git fetch</code></span>
  <span class="tradeoff-cell">Downloads new commits and moves <code>origin/main</code></span>
  <span class="tradeoff-cell">No</span>
  <span class="tradeoff-cell">Any time. It's always safe</span>
</div>
<div class="tradeoff-row">
  <span class="tradeoff-cell"><code>git pull</code></span>
  <span class="tradeoff-cell">Fetch, then move your current branch to match its copy on GitHub</span>
  <span class="tradeoff-cell">Yes</span>
  <span class="tradeoff-cell">On <code>main</code>, before you start a branch</span>
</div>
<div class="tradeoff-row">
  <span class="tradeoff-cell"><code>git rebase origin/main</code></span>
  <span class="tradeoff-cell">Replays your commits on top of the latest main</span>
  <span class="tradeoff-cell">Yes, on your branch</span>
  <span class="tradeoff-cell">Your own branch is behind and nobody else commits to it</span>
</div>
<div class="tradeoff-row">
  <span class="tradeoff-cell"><code>git merge origin/main</code></span>
  <span class="tradeoff-cell">Joins both histories with a merge commit</span>
  <span class="tradeoff-cell">Yes, on your branch</span>
  <span class="tradeoff-cell">Others also commit to the branch, or your team prefers merges</span>
</div>
</div>

The surprise is `git pull`. When I ran `git pull origin main` on my branch, git refused:

```bash
$ git pull origin main
hint: You have divergent branches and need to specify how to reconcile them.
fatal: Need to specify how to reconcile divergent branches.
```

That's git declining to guess. Ana's commits and mine both started from the same point, so there's no simple way to line them up, and current git defaults to fast-forward only: pull updates a branch only when it's behind and has nothing new of its own. On `main`, where you never commit directly, that is always the case. On a feature branch, pick rebase or merge yourself.

Rebase is peeling your sticky notes off the old binder and sticking them onto the newest edition. Merge staples the two editions together with a note saying they were combined. Both keep your work. Rebase leaves a straight line that is easier to read in review; merge keeps the history exactly as it happened.

<img src="../assets/posts/git-for-analytics-engineers/merge-vs-rebase.png" alt="Two commit graphs side by side. On the left, after git merge origin/main, the branch commit dec1e17 and main's commits 0b17664 and 54742cf join in a new merge commit. On the right, after git rebase origin/main, the history is one straight line ending in 8379303, the same change with a new hash, on top of 54742cf.">

Look at the hashes on the right. Rebase rewrote my commit: `dec1e17` became `8379303`. That matters the moment the branch is already on GitHub.

<div class="callout callout-warn">
<span class="callout-label">watch out</span>
<p>After rebasing a branch you already pushed, <code>git push</code> is rejected, and git's hint says to run <code>git pull</code>. Don't. With the default settings pull just fails again, and with merge configured it brings the old copies of your commits back, so every change appears twice. Use <code>git push --force-with-lease</code>: it overwrites your branch on GitHub only if nobody else pushed to it since your last fetch. Never rebase <code>main</code> or a branch a teammate is committing to.</p>
</div>

---

## A real change, command by command

Every analytics engineer has had this request. Telhado's operations lead writes on a Tuesday morning: capacity factor should divide by each site's installed capacity, not its peak output, and could the daily table show the inverter model too? That's one model, one metric and one new column. Here is the whole job in git, start to finish. Check your own routine against each step.

**1. Start from a fresh main.**

```bash
git switch main
git pull
```

You want `Already up to date.` or a fast-forward. If pull refuses with "divergent branches", your local `main` has commits that never went through review. Move them onto a branch with `git switch -c <name>`, then put `main` back with `git switch main` and `git reset --hard origin/main`. Run that reset only once the branch holds your commits.

**2. One branch for the request.**

```bash
git switch -c feat/capacity-factor-installed-kw
```

Both changes touch the same model and ship together, so they share a branch. If the same message also asks you to rename a dashboard field, that's a second branch.

**3. Change the model, then build it with everything downstream.**

```bash
dbt build --select fct_daily_generation+
```

The `+` builds and tests every model that depends on this one. A metric change rarely breaks the model you edited. It breaks the reporting model two steps downstream.

**4. Read your own diff before git does anything with it.**

```bash
git status
git diff
```

Only the files you meant to change should appear. If `target/`, `logs/` or a `profiles.yml` show up, they belong in `.gitignore`, not in a commit.

**5. Commit files by name, with a message about the data.**

```bash
git add models/marts/fct_daily_generation.sql
git commit -m "Use installed capacity in capacity_factor"
```

`git add .` is how a stray CSV ends up in history forever. "fix" and "wip" tell a reviewer nothing; the message should say what changes in the numbers.

**6. Push and open the pull request.**

```bash
git push -u origin feat/capacity-factor-installed-kw
```

The `-u` links your branch to its copy on GitHub, so later a plain `git push` knows where to go. In the pull request, say how the numbers moved: which sites' capacity factor went up or down, and roughly by how much. Reviewers can read SQL. They can't guess what it does to last month's report.

**7. Answer review on the same branch.**

The reviewer asks you to document the new column:

```bash
git add models/marts/schema.yml
git commit -m "Document inverter_model"
git push
```

No new branch and no new pull request. The open one picks up the commit.

**8. Catch up when main moves under you.**

Meanwhile Ana merged a change that rounds `capacity_factor` to four decimals. It's the same line you changed.

```bash
git fetch
git rebase origin/main
```

In my run, the rebase stopped with `CONFLICT (content): Merge conflict in models/marts/fct_daily_generation.sql`, and the file held both versions:

```sql
<<<<<<< HEAD
    , ROUND(kwh_generated / (peak_kw * 24), 4) AS capacity_factor
=======
    , inverter_model
    , kwh_generated / (installed_kw * 24) AS capacity_factor
>>>>>>> 3372d74 (Use installed capacity in capacity_factor)
```

During a rebase the top half, marked `HEAD`, is main's version and the bottom half is yours. Most people expect the opposite. Don't pick a side: keep both intents, Ana's rounding and your denominator, and delete the marker lines.

```sql
    , inverter_model
    , ROUND(kwh_generated / (installed_kw * 24), 4) AS capacity_factor
```

```bash
git add models/marts/fct_daily_generation.sql
git rebase --continue
dbt build --select fct_daily_generation+
git push --force-with-lease
```

Build again before pushing, because the combined line is new code nobody has run. If `--continue` opens an editor for the commit message, save and close it.

**9. Clean up after the merge.**

```bash
git switch main
git pull
git branch -d feat/capacity-factor-installed-kw
```

If your team squash-merges on GitHub, `-d` refuses with "not fully merged". A squash merge lands your work on main as one new commit, so git can't find your branch's commits inside main. Once the pull request shows Merged, `git branch -D` is safe.

When something goes sideways, three commands get you out of almost everything:

- **`git status`** first, every time. It names the state you're in and usually prints the next command.
- **`git rebase --abort`** when a rebase hits conflicts you don't want to resolve now. You land back where you started.
- **`git reflog`** when you think you lost work. It lists every place your branch has pointed, including commits that are no longer on any branch. Git keeps those entries for 30 days by default.

```bash
$ git reflog -3 fix/generation-timezone
2b9124e fix/generation-timezone@{0}: rebase (finish): ...
8379303 fix/generation-timezone@{1}: rebase (finish): ...
dec1e17 fix/generation-timezone@{2}: commit: Convert generation timestamps to Europe/Lisbon
```

Even after two rebases, the original `dec1e17` is still there. `git switch -c rescue dec1e17` would bring it back as a new branch.

<img src="../assets/posts/git-for-analytics-engineers/daily-routine.png" alt="A cheat sheet card titled the analytics engineer's git day, with four columns: start, with git switch main, git pull and git switch -c; work, with dbt build, git add and git commit; catch up, with git fetch and git rebase origin/main; share, with git push -u origin and open a pull request. A strip at the bottom lists git status, git rebase --abort and git reflog for when things go wrong.">

---

## Try this at work

<div class="callout callout-tip">
<span class="callout-label">five minutes</span>
<p>Run the three lines below once. Older git versions merged silently on pull, and <code>pull.ff only</code> makes every machine behave like current git. <code>fetch.prune</code> removes <code>origin/</code> branches that were deleted on GitHub after their pull requests merged. Then <code>git tree</code> draws the picture from this post for your own repository.</p>
</div>

```bash
git config --global pull.ff only
git config --global fetch.prune true
git config --global alias.tree "log --oneline --graph --all"
```

<div class="takeaways">
<h2>Takeaways</h2>
<ul>
<li><strong>origin/main is a photo, not a live view</strong> — <code>git status</code> compares you with your last fetch, so fetch before you trust it.</li>
<li><strong>Only three everyday commands talk to GitHub</strong> — fetch and pull download, push uploads, and everything else is local.</li>
<li><strong>Branch for every change in a team repo</strong> — a branch is a pointer, costs nothing, and keeps <code>main</code> deployable.</li>
<li><strong>Pull on main, rebase or merge on branches</strong> — current git refuses to guess when histories diverge, and that's a feature.</li>
<li><strong>Rebase rewrites hashes</strong> — after rebasing a pushed branch, use <code>--force-with-lease</code>, never pull.</li>
<li><strong>Resolve conflicts by keeping both intents</strong> — then rebuild with dbt, because the merged line is untested code.</li>
<li><strong>Almost nothing is truly lost</strong> — <code>git reflog</code> remembers where your branch has been for at least 30 days.</li>
</ul>
</div>

## Sources and version notes

Checked on 19 November 2026. I ran every command on git 2.54.0; the documentation below is current to git 2.56.1. Older git versions behave differently on `git pull` without configuration: they merged and printed a warning instead of stopping.

- [git-fetch](https://git-scm.com/docs/git-fetch), [git-pull](https://git-scm.com/docs/git-pull) and [git-rebase](https://git-scm.com/docs/git-rebase) — git reference manual, including `--ff-only` as the pull default.
- [git-push](https://git-scm.com/docs/git-push) — what `--force-with-lease` checks before overwriting.
- [git-config](https://git-scm.com/docs/git-config) — `pull.ff`, `fetch.prune` and `gc.reflogExpireUnreachable` (30 days).
- [Branches in a Nutshell](https://git-scm.com/book/en/v2/Git-Branching-Branches-in-a-Nutshell) and [Remote Branches](https://git-scm.com/book/en/v2/Git-Branching-Remote-Branches) — Pro Git.
- [The default branch for newly-created repositories is now main](https://github.blog/changelog/2020-10-01-the-default-branch-for-newly-created-repositories-is-now-main/) — GitHub changelog, 1 October 2020.

Which git command did you copy for months before you knew what it did?