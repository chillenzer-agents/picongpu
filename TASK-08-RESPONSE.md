# Task 08 -- Review response (rework)

Response to TASK-08-REVIEW.md (verdict APPROVE, 0 critical / 0 major /
4 minor / 4 nits). All rework commits are new commits on top of the
review commit a7a08fa3f; no history rewrite.

## Dispositions

| finding | disposition | commit |
|---|---|---|
| m1 PLC0414 justification factually wrong | fixed: reworded to the true reason | fd8ce76f5 |
| m2 `grid` -> `_grid` breaks keyword callers | fixed: name reverted, documented `noqa: ARG002` | ac578fcd4 |
| m3 PR-proposal numbers off | fixed: all checkable claims re-derived and corrected | 929899622 |
| m4 `[...][0]` -> `next()` changes exception type | rejected (kept), see below | - |
| n1 laser.py `= `f-string -> lazy %-format | rejected (kept), see below | - |
| n2 mid-sentence docstring wraps | partial fix: the two wraps that fit at a boundary were rewrapped, the rest are forced | a043062aa |
| n3 RUF022 sorted `__all__` | rejected (kept), see below | - |
| n4 global E721 ignore | fixed: scoped to per-file-ignores | 990a52906 |

Gate fixes found while re-verifying (not review findings):
- 97092bcf8: made ruff.toml and the PR proposal ASCII-clean (require-ascii).
- eccd04024: require-ascii exclusion for `TASK-NN-*.md` artifact docs
  (see "pre-commit gate" note below).

## Rejections with rationale and evidence

### m4 -- keep the `next()` form

All four sites are no-data/invalid-usage paths in the experimental
`extra/` plugins: three visualizers whose `self.colorbars` entries are
populated only by `visualize()` (so an all-None list only occurs when
`adjust_plot` is reached without a successful `visualize`), and png.py,
which requires at least one `.png` file in a run directory that must
exist for the rest of the function to do anything. On those states both
the old `IndexError` and the new `StopIteration` are uncaught exceptions
of a broken call, and the affected functions are not generators, so
there is no PEP 479 exposure. Restoring `IndexError` would add
try/except wrappers at four places in experimental plugin code without
functional gain. The review itself states "leaving it is defensible".

### n1 -- keep the lazy %-format logging

`all_ge` has zero in-repo call sites (`rg all_ge` matches only the
definition at `pypicongpu/laser.py:106`), and for the numeric /
list-of-numeric values its parameters carry, `%-formatting` and the
`=`-specifier produce identical strings (`str == repr` for int/float
and their lists). Today's output is byte-identical; a single-site
`# noqa: G004` would contradict the G batch's design (lazy
%-formatting) for a difference that only a future string value could
cause.

### n3 -- keep the sorted `__all__`

RUF022 is part of the `ALL` set and its fix is safe: verified in
`picmi/__init__.py` (commit aff3090ed) that the change is a pure
reordering of the same 25 members (case-insensitive alphabetical,
lowercase `constants`/`diagnostics` last). The only effect is the
cosmetic member order in Sphinx output. Reverting would require adding
a per-file-ignore/noqa exception -- against the branch's
exception-minimisation policy -- to preserve an ordering with no
semantic meaning.

## n2 -- partial fix

Rewrapped `make_lambda` (original line was 121 chars; now wraps between
the two sentences) and `apply_to_leaves` (parenthetical kept intact) in
`docs/propose_changelog.py`. The remaining E-batch wraps stay as-is:
the affected docstring line is a single sentence longer than the
120-char limit, so a boundary wrap is impossible without rewording the
text -- e.g. the module-docstring sentence in the same file is 172
chars, and the MainTest.py sentences are 167/135/125 chars.

## m3 -- measurement methodology note (one pushback)

The review measured the D/ANN/PTH magnitudes with
`ruff check --isolated`, which lints the excluded `thirdParty` tree
(42 `.py` files) under the default target version. Measured against the
config's actual lint scope (real `ruff.toml` with the family's ignore
temporarily removed, ruff 0.12.10): D 3793, ANN 2451, PTH 110,
TRY+EM 608, TID252 80. In particular the proposal's original
"PTH (~110)" was already correct; the isolated-run figure of 248
includes thirdParty. The D/ANN/TID252 figures were still off and are
corrected to the scope-accurate values in both the proposal and the
`ruff.toml` comments.

## pre-commit gate note (review claim not reproducible)

The review's claim that `pre-commit run --all-files` passed at the old
tip 0b1ba15d0 is not reproducible: the `require-ascii` hook fails on
the non-ASCII `TASK-08-PR-PROPOSAL.md` as committed at that tip
(verified by running the cached hook script on the file). At the
review commit a7a08fa3f it additionally failed on
`TASK-08-REVIEW.md` itself. This matches the coordinator's
cross-cutting note about `require-ascii` being red on other branches'
tips. Fixed here by making the author-controlled files ASCII-clean
(97092bcf8) and adding a documented `require-ascii` exclusion for the
per-task artifact docs, which are documentation (like the already
excluded rst files and CHANGELOG.md) and which the author must not
modify (eccd04024).

## Final gate results (ruff 0.12.10, pre-commit 4.3.0)

- `ruff check .` -> 0 violations
- `ruff format --check .` -> 0 diffs (291 files)
- `cd lib/python/test/picongpu && python -m pytest quick/ -q` ->
  174 passed, 2 xfailed, 1 xpassed (identical to baseline)
- `pre-commit run --all-files` -> all hooks pass
