# ChaseBench — `doctors-fd` scenario, in Vadalog

A runnable transcription of the `doctors-fd` scenario of
[ChaseBench](https://github.com/dbunibas/chasebench) (`scenarios/doctors-fd`) into the
dialect accepted by `vadalog-portable`. It is versioned with the repository but ships
in no wheel and in no release; whatever a run writes under `out*/` is ignored by git.
Provenance and citation: [`../README.md`](../README.md).

`doctors-fd` is [`doctors`](../doctors/) **minus two EGDs**. The source data, the
source-to-target TGDs and the queries are byte for byte the same in ChaseBench; what is
removed are the two dependencies that tie `targethospital` to `doctor`:

```
targethospital(?doctor,?spec,?hospital1,?npi1,?hconf1),
doctor(?npi2,?doctor,?spec,?hospital2,?conf2) -> ?hospital1 = ?hospital2 .   % gone
                                              -> ?npi1     = ?npi2     .   % gone
```

What is left is functional dependencies on the target relations alone — `id` is a key
of `prescription`, `npi` and the doctor's name are keys of `doctor` — and nothing that
can turn an invented hospital into a constant. The pair is worth having side by side:
same instance, same TGDs, two dependencies fewer, and the difference is visible
fact by fact.

Because the data is identical, this directory does not carry a second copy of it: the
`@bind` paths point at `../doctors/data`.

## Files

| File | Contents |
|---|---|
| `rules.vada` | the five s-t TGDs and the eight target EGDs |
| `inputs-10k.vada`, `-100k`, `-sample` | `@input` / `@bind` / `@mapping`, bound to `../doctors/data/<size>` |
| `doctors-fd.vada` | driver for the 10k instance |
| `doctors-fd-100k.vada`, `doctors-fd-sample.vada` | the other two instances |
| `doctors-fd-queries.vada` | the nine benchmark queries on the chased instance |

## Running

```sh
python3 ../../dist/vadalog.pyz run doctors-fd-sample.vada
python3 ../../dist/vadalog.pyz run doctors-fd.vada --format csv --out out
python3 ../../dist/vadalog.pyz run doctors-fd-queries.vada --format csv --out out-queries
```

## Results obtained (10k), against `doctors`

The chase closes in 3 rounds and about 4 s, with nothing suppressed by the
isomorphism check. The relations come out the same size as in `doctors` — dropping an
EGD changes which nulls get bound, not which facts exist — but not with the same
contents:

| | `doctors` | `doctors-fd` |
|---|---|---|
| `doctor` | 997 | 997 |
| `prescription` | 7 900 | 7 900 |
| `targethospital` | 837 | 837 |
| `doctor` facts whose hospital is still a null | 96 | **497** |

The 497 are every doctor known only through `medprescription`: in `doctors` the
`targethospital` EGD matched 401 of them on `(doctor, spec)` and replaced the invented
hospital by the real one, and here nothing does.

That difference reaches exactly one query. `q05` joins a doctor's hospital against a
`targethospital` hospital, and a marked null never equals a constant:

| Query | `doctors` | `doctors-fd` |
|---|---|---|
| `q01` | 837 | 837 |
| `q02` | 6 998 | 6 998 |
| `q03` | 6 998 | 6 998 |
| `q04` | 6 998 | 6 998 |
| `q05` | 842 | **440** |
| `q06` | 6 998 | 6 998 |
| `q07` | 837 | 837 |
| `q08` | 22 | 22 |
| `q09` | 19 | 19 |

On the 100k instance the chase takes about 4 m 30 s for 177 500 facts — 1 000
`doctor`, 79 000 `prescription`, 1 000 `targethospital` — of which 500 `doctor` facts
keep a null hospital, against none in `doctors`.

Every number above was reproduced by an independent Python computation of the same
chase and the same queries over the same files, and the eight functional dependencies
were checked to hold on the engine's own output.
