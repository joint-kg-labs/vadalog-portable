# ChaseBench — `deep` scenario, in Vadalog

A runnable transcription of the `deep` scenario of
[ChaseBench](https://github.com/dbunibas/chasebench) (`scenarios/deep`) into the
dialect accepted by `vadalog-portable`. It is versioned with the repository, data
included, but ships in no wheel and in no release; whatever a run writes under `out*/`
is ignored by git. Provenance and citation: [`../README.md`](../README.md).

Where [`doctors`](../doctors/) is about EGDs and [`LUBM`](../LUBM/) about an ontology
over real data, `deep` is the **chase-termination stress test**, generated rather than
modelled. A thousand source relations of one row each feed a thousand source-to-target
TGDs; every rule writes three target atoms, of which only the first is bound by the
body, so each activation mints six marked nulls and chains two of the new atoms
through a shared one. On top of that sit 100, 200 or 300 target TGDs of the same
shape, recursive over the target relations. There are no constants to anchor anything:
after the first step the instance is made almost entirely of nulls, which is exactly
what the scenario is built to punish.

## Files

| File | Contents |
|---|---|
| `inputs.vada` | `@input` / `@bind` for the 1000 source relations `v0`…`v999` |
| `st-tgds.vada` | the 1000 source-to-target TGDs, shared by the three variants |
| `t-tgds-100.vada`, `-200`, `-300` | the target TGDs of each variant |
| `deep-100.vada`, `-200`, `-300` | drivers: inputs + rules + `@output` of all 299 target relations |
| `deep-100-queries.vada`, `-200`, `-300` | the same plus the benchmark queries |
| `data/` | 1000 single-row CSVs, 21 KB in total, copied unchanged from ChaseBench |

The three variants share their data, their schema and their source-to-target TGDs and
differ only in the number of target TGDs and in their queries, so those parts are
written once. Variants 100 and 200 ship twenty queries each; variant 300 ships a
single one, named `q`, which is how ChaseBench distributes it.

## Running

From this directory:

```sh
python3 ../../dist/vadalog.pyz run deep-100.vada --format csv --out out-100
python3 ../../dist/vadalog.pyz run deep-100-queries.vada --format csv --out out-q100
```

Each of the three chases takes about 1.3 s, and the queries add almost nothing.

## Results obtained

| Variant | Rules | Derived facts | Rounds | Suppressed | Chase |
|---|---|---|---|---|---|
| 100 | 1000 + 100 | 2 892 | 4 | 3 887 | 1.3 s |
| 200 | 1000 + 200 | 3 015 | 5 | 6 857 | 1.3 s |
| 300 | 1000 + 300 | 3 138 | 5 | 10 022 | 1.4 s |

Query answers, variant 100: `q01` 4, `q02` 4, `q03` 5, `q04` 4, `q05` 2, `q06` 3,
`q07` 2, `q08` 3, `q09` 3, `q10` 1, `q11` 3, `q12` 2, `q13` 1, `q14` 1, `q15` 2, `q16`
… `q20` 1 each. Variant 200: 3, 3, 3, 4, 4, 2, 2, 4, 4, 2, 2, then 1 each. Variant
300: the single query returns 1.

## What this scenario actually shows

`deep` terminates here in a second and a half, where it is meant to be the case that
breaks a chase engine. That is not a free lunch, and the figures say where the
difference went. **More facts are suppressed than kept**: 3 887 against 2 892 in
variant 100, and better than three to one in variant 300. The suppression is the
isomorphism check that gives the chase its termination guarantee
(SPECIFICATION.md §7.4) — a candidate fact isomorphic to one already derived is
discarded — and in a scenario whose tuples are all nulls, almost everything is
isomorphic to something already there.

Two consequences, both measured rather than assumed.

**The output is not a model of the dependencies.** Every target TGD is violated — all
100 of them in variant 100, all 200 in variant 200, all 300 in variant 300 — and so
are about 715 of the 1000 source-to-target TGDs (715, 713 and 713 respectively). A
body matches and the head witness it would need was suppressed as isomorphic, which in
a scenario whose tuples are nearly all nulls is the common case rather than the
exception.

**The certain answers are right anyway.** An independent restricted chase, written
without the engine and with no isomorphism filter, produces 21 522 facts for variant
100 (against the engine's 2 892), 996 678 for variant 200 (330 times the engine's
3 015), and passes two million for variant 300 before the check gives up. Evaluating
the benchmark queries over that much larger instance and keeping only the answers free
of nulls gives, query by query, exactly what the engine returns — including the two
cases where the reference has more answers than the engine (`q02` of variant 100: 22
answers, 4 of them certain, and the engine returns those 4) and the one case where the
only answer contains a null in both (`q15` of variant 200).

So on `deep` the engine computes a sound and complete set of certain answers out of an
instance that is one to three orders of magnitude smaller than the chase itself, and
is not a model of the input dependencies. That is a good trade for query answering and
a bad one for anyone wanting the chased instance as a materialisation, and it is worth
having on record before §13.1 is revisited.
