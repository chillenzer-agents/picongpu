.. _development-release-automation:

Release Automation: Level 2 + Level 3 Design
============================================

.. note::

   Status: **exploratory design + proof-of-concept**. This document proposes
   how to automate the zenodo/contributors maintenance step (release automation
   "Level 2") and where such automation should live ("Level 3"), following
   `TT-21 <https://github.com/chillenzer/picongpu/issues/50>`__ (split from
   `TT-05 <https://github.com/chillenzer/picongpu/issues/34>`__). Nothing in
   the shipped release process is changed yet; a follow-up implementation task
   will be derived once this design is accepted.

Background
----------

The maintainer runbook (``email-release.txt``) requires, before every release:

1. update ``.zenodo.json``
   (move old creators → contributors ``"type": "Other"``; only people who added
   commits within the release range stay in ``creators``),
2. keep the README team list in sync (ideally by pointing README at the zenodo
   / a ``Contributors`` file),
3. create the ``release-*.*.*`` branch, prepare the changelog, adjust versions.

Two recurring problems motivated this exploration:

* **Zenodo is a manual chore and prone to error.** The 0.8.0 run had the zenodo
  PR merged into ``dev`` instead of the release branch
  (`#5235 <https://github.com/ComputationalRadiationPhysics/picongpu/pull/5235>`__ /
  `#5239 <https://github.com/ComputationalRadiationPhysics/picongpu/pull/5239>`__),
  exactly the failure mode the email warns about.
* **Git identities are badly configured.** The same person frequently commits
  from several machines with different ``git user.name``/``user.email``, so a
  naive "creators == ``git log %an`` committers" is wrong. Real examples from
  the ``0.7.0..0.8.0`` range are shown in
  `Identity aliasing (the core requirement)`_.

This task covers the two higher automation levels:

* **Level 2 — zenodo & contributors automation** (identity-aware creator
  derivation, ORCID/affiliation sidecar, wrong-branch guard),
* **Level 3 — CI home** (does release automation run as a GitLab job, a GitHub
  Actions workflow, or a maintainer-side script?).

Level 1 (TT-05) already added ``share/ci/release_check.sh`` plus the version
bump fixes; this design cross-checks with that checklist and the upstream
`#5728 <https://github.com/ComputationalRadiationPhysics/picongpu/pull/5728>`__
(removing the hard-coded README team list).

Level 2: Zenodo & contributors automation
-----------------------------------------

Pipeline (what the PoC implements)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

::

   git log <prev>..<cand> --use-mailmap --format=%an|%ae
        │  raw (name, email, count)
        ▼
   skip list (bot/CI/maintenance) ──► dropped
        ▼
   alias table (email/name → person) + email grouping
        ▼
   deduplicated people in range      git log --use-mailmap (whole history)
        │                                  │
        │  creators                       │  people minus creators
        ▼                                  ▼
   ┌────────────────────────────────────────────────────┐
   │ proposed .zenodo.json: creators + contributors(Other) │
   │ ORCID/affiliation carried from existing .zenodo.json  │
   └────────────────────────────────────────────────────┘

The input is the set of commit authors in ``git log <prev>..<cand>``
(``%an`` = name, ``%ae`` = email), which is also the input the L1 checklist
already diffs. Output is a *proposal*: a unified diff of ``.zenodo.json`` plus a
human-readable resolution table. The tool never writes ``.zenodo.json``.

Identity aliasing (the core requirement)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

A single "person" appears under many raw identities. The design uses **two
complementary artifacts** (recommended option **A + B**):

* **Option A — ``.mailmap`` + ``git log --use-mailmap``.** This is the
  git-native way to normalise names and addresses (``Proper Name <proper@email>``
  lines, ``<proper@email> Other <other@email>`` merges). It is reusable by git
  itself, ``git shortlog``, etc. The PoC passes ``--use-mailmap`` whenever a
  ``.mailmap`` exists.
* **Option B — ``contrib/aliases.json``.** A checked-in, zenodo-specific skip
  and merge table:

  * ``people``: canonical person keys with a zenodo display name
    (``"Last, First"``), a canonical email and a list of ``aliases`` (further
    emails or raw git names used by that human from other machines),
  * ``skip``: bot/CI/maintenance identities to drop (`dependabot`, `renovate`,
    `github-actions`, `gitlab-ci`, ``root@...``, ``noreply@github.com``, the
    terok/opencode gate identity, generic ``[bot]`` accounts, project-wide mail
    addresses like ``picongpu@hzdr.de`` / ``tools@hzdr.de``).

  Unknown identities (no alias entry) are **not** silently merged or dropped —
  they are surfaced with a ``NEEDS-HUMAN-ATTRIBUTION`` marker.

Why ``.mailmap`` alone is not enough: it can merge *known* identities but gives
no explicit way to drop bots, and people who never bothered to configure git
need a separate, project-curated list. Conversely, ``aliases.json`` alone would
re-implement mailmap. Hence A + B, with ``aliases.json`` as the "escape hatch"
until ``.mailmap`` is complete.

Concrete multi-machine example (from ``0.7.0..0.8.0``)
""""""""""""""""""""""""""""""""""""""""""""""""""""""

.. list-table:: Raw identities vs canonical people
   :header-rows: 1

   * - raw identity (name | email)
     - canonical person
     - how merged
   * - ``Julian Lenz|j.j.lenz@swansea.ac.uk``
     - Lenz, Julian
     - email alias
   * - ``Julian Lenz|j.lenz@hzdr.de``
     - Lenz, Julian
     - email alias
   * - ``chillenzer|107195608+...@users.noreply.github.com``
     - Lenz, Julian
     - manual alias (merge-bot)
   * - ``Tapish|narwal83@hzdr.de``
     - Narwal, Tapish
     - manual alias
   * - ``Tapish Narwal|10693329+ikbuibui@users.noreply.github.com``
     - Narwal, Tapish
     - manual alias
   * - ``JessicaTiebel|j.tiebel@hzdr.de``
     - Tiebel, Jessica
     - email alias
   * - ``Tiebel|tiebel93@hemera5.cluster``
     - Tiebel, Jessica
     - manual alias (cluster)
   * - ``Klaus Steiniger|k.steiniger@hzdr.de``
     - Steiniger, Klaus
     - email grouping
   * - ``steindev|k.steiniger@hzdr.de``
     - Steiniger, Klaus
     - email grouping
   * - ``Richard Pausch|r.pausch@hzdr.de``
     - Pausch, Richard
     - email grouping
   * - ``PrometheusPi|r.pausch@hzdr.de``
     - Pausch, Richard
     - email grouping
   * - ``FilipO28555|filipoptolowicz@gmail.com``
     - Optołowicz, Filip
     - email grouping
   * - ``Filip Optołowicz|filipoptolowicz@gmail.com``
     - Optołowicz, Filip
     - email grouping
   * - ``Third Party|picongpu@hzdr.de``
     - *(dropped)*
     - skip
   * - ``Tools|tools@hzdr.de``
     - *(dropped)*
     - skip
   * - ``s0134766|s0134766@login2.alpha.hpc.tu-dresden.de``
     - *(unknown, surfaced)*
     - needs human

Same-email-different-name pairs collapse automatically via email grouping; the
same-person-different-email pairs need an explicit alias entry. HPC login-node
accounts are ambiguous (a real human on a shared machine) and are therefore
surfaced, not auto-skipped.

Creators vs contributors
^^^^^^^^^^^^^^^^^^^^^^^^

* **Creators** = deduplicated people who committed into the release range
  ``git log <prev>..<cand>`` (after skip/alias).
* **Contributors** = every other distinct person in the repository history
  (whole ``git log --use-mailmap``), minus bots, rendered with
  ``"type": "Other"`` — this implements the email recipe "move old creators to
  contributor add (type Other)".

ORCID / affiliation: human sidecar
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The tool **never guesses** ORCIDs or affiliations. It:

1. carries over existing ORCID/affiliation from the current ``.zenodo.json`` for
   names that match,
2. prints the proposed creator/contributor table for people to confirm,
3. leaves a human-verified sidecar (``contrib/zenodo_people_meta.json`` or the
   ``people`` entries of ``aliases.json``) as the source of truth to fill in.

Wrong-branch guard
^^^^^^^^^^^^^^^^^^

The zenodo PR must target the **release branch**, never ``dev`` (the historical
``#5235``/``#5239`` failure). The PoC implements ``--check-release-branch
<ref>`` which asserts the candidate ref is reachable from a local ``release-*``
branch and refuses to proceed otherwise. The requirement should also be encoded
in the zenodo PR template / checklist (cross-link with TT-05 L1) by making the
diff step fail outside a ``release-*`` branch.

README / Contributors sync
^^^^^^^^^^^^^^^^^^^^^^^^^^

The same alias table is the natural single source for a generated
``CONTRIBUTORS`` (canonical names) file that README points to, replacing the
hard-coded "Active Team / Maintainers / Former Members" block (coordinates with
upstream `#5728 <https://github.com/ComputationalRadiationPhysics/picongpu/pull/5728>`__).
Decision for the implementation task: generate the file during release as part
of the same pipeline as ``.zenodo.json`` (keeps everything derived from one
artifact), rather than a one-time consolidation.

Level 3: CI home
----------------

Three options were considered:

**Option G — GitLab job.** A ``.gitlab-ci`` "release" job gated on
``CI_COMMIT_TAG``/a ``release-*`` branch rule that runs the L1 checklist and the
L2 derivation, then posts/creates the draft release. Consistent with the
project's GitLab-first CI and has more runners/capacity. Costs: ``gh`` needs a
GitHub token with ``contents:write`` plumbed through GitLab CI variables; the
release is created from GitLab but targets GitHub Releases, which is indirect.

**Option H — GitHub Actions workflow.** A ``.github/workflows/release.yml`` with
a ``workflow_dispatch`` / tag trigger doing the same. GitHub-native release API
and the natural home of ``gh release create --draft``; runs where the release
object lives. Costs: introduces a *second* CI platform where none exists today;
cannot easily reuse the GitLab matrix; still only "assists" the human final
step.

**Option M — maintainer-side script only.** Keep automation in the L1 script
(plus L2 in ``contrib``); no CI home decision. Simplest, nothing new to run in
CI, works for the (deliberately) rare, step-by-step release ceremony. Costs:
nothing runs automatically; relies on discipline.

Decision matrix
^^^^^^^^^^^^^^^

.. list-table:: Level 3 decision matrix
   :header-rows: 1

   * - criterion
     - GitLab G
     - Actions H
     - Script M
   * - fits existing CI
     - + +
     - — —
     - n/a
   * - release credential home
     - — (cross-platform token)
     - + +
     - + +
   * - auto triggers on tag
     - + +
     - + +
     - —
   * - runs where release lives
     - —
     - + +
     - +
   * - gh release create --draft
     - + +
     - + +
     - + +
   * - new CI platform needed
     - no
     - yes
     - no
   * - human still confirms UI
     - always
     - always
     - always

**Recommendation: GitHub Actions (H), with the script (M) as the always-usable
fallback.** The deciding factors: the release artefact is a GitHub Release, so
the token lives where it is used; ``workflow_dispatch``/tag triggers are
exactly the "create the draft release" ceremony from the email; and GitHub was
explicitly confirmed acceptable by the requester (the "more resources on
GitLab" remark is about capacity, not a restriction). GitLab stays the
project's *test* home; the *release* home becomes GitHub. The inherently human
steps (writing release notes from the changelog summary, choosing the target
branch in the GitHub UI, DOI badge) can only be assisted, not automated.

PoC
---

Two artifacts accompany this document:

* ``contrib/gen_zenodo_creators.py`` — the identity-aware derivation (Level 2).
* ``contrib/aliases.json`` — the skip/merge table (Level 2, option B).

Usage::

   python contrib/gen_zenodo_creators.py --repo <repo> --range 0.7.0..0.8.0
       [--aliases contrib/aliases.json] [--no-mailmap] [--no-diff]
       [--check-release-branch 0.8.0]

The script runs ``git log --use-mailmap``, applies skip/merge aliases, dedups,
and prints creators, contributors ("type": "Other"), skipped identities, an
optional wrong-branch-guard verdict, and the proposed ``.zenodo.json`` diff
with ORCID/affiliation carried over for matching names.

Validation: ``0.7.0..0.8.0``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Running the PoC against the real ``0.7.0..0.8.0`` range
(1,395 commits, historical creators = 20) yields **22 creators** after
identity-aware dedup:

* the **20 people** present in the historical 0.8.0 ``creators`` are reproduced
  exactly (the three Julian-Lenz identities collapse into one; ``PrometheusPi``
  merges into Pausch, ``steindev`` into Steiniger, cluster/`hemera`/GitHub
  noreply accounts merge into their people),
* plus **2 surfaced for human review**: ``Optołowicz, Filip`` (21 commits in
  range, missing from the historical file) and an *unknown* HPC login-node
  identity ``s0134766@login2.alpha.hpc.tu-dresden.de`` (1 commit, cluster
  profile update) which is deliberately flagged, not auto-merged.

21 raw identities were dropped as bots/CI (`Third Party`/`Tools` under
``picongpu@hzdr.de``/``tools@hzdr.de``). Contributors = 78 distinct people from
the rest of history. This matches the historical structure and demonstrates the
dedup/bot-exclusion/surface-unknown behaviour the requester asked for.

Tests
^^^^^

``contrib/tests/test_gen_zenodo_creators.py`` builds a synthetic git repo with
deliberately inconsistent identities and asserts: multi-identity dedup, bot
exclusion, unknown identities surfaced (not merged), and the wrong-branch guard
pass/fail behaviour. Run with ``pytest contrib/tests``.

Open questions for the requester
--------------------------------

1. **Aliasing preference** — ``.mailmap`` + ``contrib/aliases.json`` (A+B) is
   recommended; confirmation that the checked-in ``contrib/aliases.json`` is
   acceptable is sought (it is new).
2. **Creators scope** — strictly committers-in-range (the email's literal
   reading, may change the creator list, e.g. Filip, and drops anyone with no
   commits in range) vs the historical "the usual release contributors with
   ORCIDs" practice. The PoC implements the former and *surfaces* the
   difference instead of hiding it.
3. **CI home** — design recommends GitHub Actions (H) with the script (M) as
   fallback; requester confirmed GitHub remains in play.
4. **Bot/CI skip list** — the PoC ships one (including the terok/opencode gate
   identity and project mail addresses); additions welcome.

Follow-up (implementation task)
-------------------------------

1. Add ``.mailmap`` (subset needed for release identity merging) or keep
   ``aliases.json`` as the sole table (validate against the next release range).
2. Wire the derivation into the release workflow: generate ``.zenodo.json``
   diff, ORCID sidecar review, wrong-branch guard in the PR template.
3. Add ``CONTRIBUTORS`` generation from the same alias table; point README at
   it (coordinate with upstream `#5728 <https://github.com/ComputationalRadiationPhysics/picongpu/pull/5728>`__).
4. Implement the Level 3 recommendation as a GitHub Actions workflow prototype
   (trigger + L1 checklist call + ``gh release create --draft``, dry-run only).
