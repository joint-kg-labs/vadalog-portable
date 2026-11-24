# ChaseBench — `doctors` scenario, in Vadalog

A runnable transcription of the `doctors` scenario of
[ChaseBench](https://github.com/dbunibas/chasebench) (`scenarios/doctors`) into the
dialect accepted by `vadalog-portable`. It is versioned with the repository, data
included, but ships in no wheel and in no release; whatever a run writes under `out/`
is ignored by git. Provenance and citation: [`../README.md`](../README.md).

`doctors` is a data-exchange scenario: five source-to-target TGDs, three of which have
**existential head variables**, and ten target **EGDs** that turn the resulting marked
nulls into constants. It is the smallest scenario in the benchmark that exercises the
TGD/EGD interaction end to end, which makes it a good functional test of the chase.

## Files

| File | Contents |
|---|---|
| `rules.vada` | the five s-t TGDs and the ten target EGDs (the dependencies, verbatim in Vadalog syntax) |
| `inputs-10k.vada` | `@input` / `@bind` / `@mapping` for the four source relations, 10k instance |
| `inputs-100k.vada` | the same, 100k instance |
| `inputs-sample.vada` | the same, tiny sample instance |
| `doctors.vada` | driver: 10k inputs + rules + `@output` of the three target relations |
| `doctors-100k.vada` | driver for the 100k instance |
| `doctors-sample.vada` | driver for the sample — a few seconds, good for eyeballing the nulls |
| `doctors-queries.vada` | 10k inputs + rules + the nine benchmark queries `q01`…`q09` |
| `data/10k`, `data/100k` | source CSVs, copied unchanged from ChaseBench |
| `data/sample` | 10 treatments / 10 medprescriptions / 10 physicians / 12 hospitals, carved out of `10k` so that every join and every EGD still fires |

## Running

From this directory (the `@bind` paths are relative to the program file):

```sh
python3 ../../dist/vadalog.pyz run doctors-sample.vada              # facts on stdout
python3 ../../dist/vadalog.pyz run doctors.vada --format csv --out out
python3 ../../dist/vadalog.pyz run doctors-queries.vada --format csv --out out-queries
```

`--csv-dir` is not needed and should not be used: it would also redirect the input
paths. Marked nulls print as `z1`, `z2`, … in `facts` format and as `\N` in CSV.

## The scenario

Source schema: `hospital(doctor, spec, hospital, npi, conf)`,
`medprescription(id, patient, npi, doctor, spec, conf)`,
`physician(npi, name, spec, conf)`, `treatment(id, patient, hospital, npi, conf)`.

Target schema: `doctor(npi, doctor, spec, hospital, conf)`,
`prescription(id, patient, npi, conf)`,
`targethospital(doctor, spec, hospital, npi, conf)`.

The TGDs invent a null for every `conf`, and a null for the `hospital` of a doctor known
only through `medprescription`. The EGDs then say that `id` is a key of `prescription`,
that `npi` and the doctor's name are both keys of `doctor`, and that `targethospital`
pins down the hospital and the npi of a doctor. Chasing therefore merges the per-tuple
nulls per key and, wherever a `targethospital` fact matches on `(doctor, spec)`, replaces
the null hospital by a constant — the behaviour worth watching in the sample output.

Note that the ChaseBench distribution ships two variants of the dependencies:
`dependencies/` (used here) and `ST-ONLY/dependencies/`, which drops the EGDs.

## Results obtained (10k)

| Relation | Facts |
|---|---|
| `doctor` | 997 (96 of them still with a null hospital) |
| `prescription` | 7 900 |
| `targethospital` | 837 |

| Query | Answers | | Query | Answers |
|---|---|---|---|---|
| `q01` | 837 | | `q06` | 6 998 |
| `q02` | 6 998 | | `q07` | 837 |
| `q03` | 6 998 | | `q08` | 22 |
| `q04` | 6 998 | | `q09` | 19 |
| `q05` | 842 | | | |

Every one of these numbers was cross-checked against an independent Python computation of
the same chase and the same queries over the same input files.

Timings on the 10k instance (CPython 3.10, single core): the chase takes ≈ 2.5 s
(734 790 activations, 20 571 facts, 3 rounds), the chase plus the nine queries ≈ 5.2 s.
The 100k instance is a stress case: ≈ 2 m 30 s for the chase alone (57.9 M activations,
177 500 facts), giving 1 000 `doctor` facts — none with a null hospital — 79 000
`prescription` facts and 1 000 `targethospital` facts.

## Caveats

* The EGDs equate constants wherever two source tuples disagree, which would abort the
  run with a unification failure. The ChaseBench input files are consistent — this was
  verified on `data/10k` before transcribing — so the chase succeeds.
* `q08` and `q09` contain the hospital constants `"HH65795"` and `"HH30727"`, which come
  from the `queries/10k` variant of the query files. Against another instance size they
  would have to be replaced by the constants in the corresponding `queries/<size>` files.
* `vadalog check --strict doctors.vada` is clean: the harmless-EGD condition of the
  specification (§5.5) holds for this scenario, so the EGDs never have to be applied to a
  position carrying a repeated variable or a constant in an unsafe way.
