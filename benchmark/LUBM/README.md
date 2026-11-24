# ChaseBench — `LUBM` scenario, in Vadalog

A runnable transcription of the `LUBM` scenario of
[ChaseBench](https://github.com/dbunibas/chasebench) (`scenarios/LUBM`) into the
dialect accepted by `vadalog-portable`. It is versioned with the repository, data
included, but ships in no wheel and in no release; whatever a run writes under `out/`
is ignored by git. Provenance and citation: [`../README.md`](../README.md).

Where [`doctors`](../doctors/) is about **EGDs**, LUBM is about **scale and
recursion**: 30 source-to-target TGDs that rename the source relations, and 106
target TGDs that are the LUBM university ontology — class inclusions, domain and
range axioms, a transitive `subOrganizationOf`, and nine rules with an existential
head variable (the department a chair must head, the organisation an employee must
work for, the course a student must take). Twenty-five of the target predicates are
mutually recursive.

## Files

| File | Contents |
|---|---|
| `rules.vada` | the 30 s-t TGDs and the 106 target TGDs |
| `inputs-001.vada` | `@input` / `@bind` for the 30 source relations, `001` instance |
| `inputs-sample.vada` | the same, sample instance |
| `LUBM.vada` | driver: `001` inputs + rules + `@output` of all 50 derived predicates |
| `LUBM-sample.vada` | driver for the sample — a third of a second, for eyeballing |
| `LUBM-queries.vada` | `001` inputs + rules + the fourteen benchmark queries `q01`…`q14` |
| `data/001` | source CSVs for one university, 100 543 rows over 30 relations, copied unchanged from ChaseBench |
| `data/sample` | the `Department0-University0` slice of `001`, 8 297 rows, so that all fourteen queries still have their constants |

The larger instances (`010`, `100`, `01k` — 90 MB to 528 MB) are not committed; take
them from ChaseBench and drop them under `data/` with an `inputs-<size>.vada` of their
own if you want them.

## Running

From this directory:

```sh
python3 ../../dist/vadalog.pyz run LUBM-sample.vada --format csv --out out
python3 ../../dist/vadalog.pyz run LUBM.vada --format csv --out out
python3 ../../dist/vadalog.pyz run LUBM-queries.vada --format csv --out out-queries
```

Every column of every source relation is a `SYMBOL`, i.e. a string, so no `@mapping`
is needed: without one the reader types every field as a string. Predicate names are
the benchmark's own with the first letter lower-cased — `GraduateStudent` becomes
`graduateStudent` — because a Vadalog identifier cannot start upper-case. Marked
nulls print as `z1`, `z2`, … and are written `\N` in CSV.

## Results obtained (`001`, one university)

100 543 source facts in, 249 954 facts in the chased instance after 7 rounds, of
which 149 411 are the 50 derived target relations. The chase takes ≈ 2.7 s on
CPython 3.10, the chase plus the fourteen queries ≈ 3.3 s. The sample takes 0.3 s.
The largest derived relations are `takesCourse` 29 279, `name` 15 972,
`publicationAuthor` 10 634, `member` and `memberOf` 9 417 each, `person` 8 330,
`student` 7 790.

| Query | Answers | | Query | Answers | | Query | Answers |
|---|---|---|---|---|---|---|---|
| `q01` | 4 | | `q06` | 7 790 | | `q11` | 224 |
| `q02` | 0 | | `q07` | 67 | | `q12` | 15 |
| `q03` | 6 | | `q08` | 7 790 | | `q13` | 1 |
| `q04` | 34 | | `q09` | 208 | | `q14` | 5 916 |
| `q05` | 719 | | `q10` | 4 | | | |

`q02` returning nothing is a property of the data, not a failure: on a single
university no graduate student has an undergraduate degree from the university their
own department belongs to. All fourteen counts, on `001` and on the sample alike,
were reproduced by an independent Python evaluation over the engine's own output.

## Two things worth knowing

**The query bodies are reordered.** The engine orders body atoms with a simple static
heuristic and has no cost model, so a conjunctive query written class-atoms-first —
which is how LUBM writes them — is evaluated as a near cross product of the classes
before any join key is bound: `q09` (`Student`, `Faculty`, `Course`, then the three
joins) did not finish in ninety seconds. The transcription therefore orders each body
greedily — an atom with a constant first, then binary atoms connected to what is
already bound, unary class atoms last — after which every query answers in the three
seconds above. The reordering is semantics-preserving; the queries are the
benchmark's, atom for atom.

**The chased instance is not literally a model of the dependencies.** Six of the 136
rules are violated by the output, always on facts whose arguments are all marked
nulls: `course(X) :- graduateCourse(X)` has `graduateCourse(z1)` without `course(z1)`,
and likewise for `organization`, `worksFor`/`headOf`, `member`, `researchGroup` and
`teachingAssistantOf`. The cause is the isomorphism check that gives the chase its
termination guarantee (SPECIFICATION.md §7.4): for a recursive predicate, a candidate
fact isomorphic to one already derived is discarded, and all all-null unary facts of a
predicate are isomorphic to each other, so exactly one survives — 1 `course(z)` fact
against 1 628 `course` facts overall, 1 `organization(z)` against 1 219, and so on.
Facts mixing a constant with a null are unaffected, 11 479 of them being kept. The
certain answers are unaffected too: the fourteen queries all project constants, which
is why the independent check reproduces every count. It is nonetheless the clearest
demonstration in this repository of what §13.1 gives up by dropping the warded
rewriting, and worth re-reading if the termination strategy is ever revisited.
