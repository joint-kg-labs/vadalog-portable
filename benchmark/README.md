# Benchmarks

Scenarios from **ChaseBench** transcribed into Vadalog, with the benchmark's own
source data, so that a clone is enough to run one. They are real workloads rather
than teaching examples, and they are the counterpart of `examples/`: those show
what the language looks like, these show what the chase does under load.

| Scenario | What it exercises |
|---|---|
| [`doctors`](doctors/) | data exchange: five source-to-target TGDs with existential head variables, ten target EGDs that merge the resulting marked nulls and resolve them to constants |
| [`doctors-fd`](doctors-fd/) | the same scenario with the two EGDs that bind an invented hospital removed: same facts, 497 nulls left unresolved instead of 96, and one query answer out of nine that changes |
| [`LUBM`](LUBM/) | scale and recursion: 30 source-to-target TGDs and the 106 target TGDs of the university ontology, 25 mutually recursive predicates, a transitive closure, nine existential heads, 100k source facts |
| [`deep`](deep/) | chase termination: 1000 source-to-target TGDs and 100, 200 or 300 recursive target TGDs, all with existential heads, over an instance that is almost entirely marked nulls |
| [`STB-128`](STB-128/) | scale: an iBench-generated data-exchange scenario, 111 source relations of 10 000 rows, 160 s-t TGDs, 39 target TGDs and 93 target EGDs, three million facts |
| [`Ontology-256`](Ontology-256/) | more scale: 218 source relations, 256 s-t TGDs, 273 target TGDs, 348 target EGDs, seven million facts — the largest thing the engine has been run on |

Each scenario has a README of its own with the commands, the expected answer sizes
and the timings. `doctors`, `LUBM` and `deep` carry their data here; the two iBench
scenarios are 209 MB and 482 MB unpacked, far too large to version, so each has a
`fetch-data.sh` that downloads its data from ChaseBench into an ignored `data/`.
Nothing here is distributed: no wheel, no `vadalog.pyz`, no binary,
no release asset carries it, and `tests/test_pyz.py` checks that it stays that way.
Whatever a run writes under `out/` or `out-*/` is ignored by git.

## Provenance

The dependencies, the queries and the CSV data come from the ChaseBench repository,
<https://github.com/dbunibas/chasebench>, and are reproduced here unchanged except
for the transcription of the dependencies and queries into Vadalog syntax. The
benchmark is the work of its authors, not of this project:

> M. Benedikt, G. Konstantinidis, G. Mecca, B. Motik, P. Papotti, D. Santoro,
> E. Tsamoura. *Benchmarking the Chase.* PODS 2017, 37–52.
> [doi:10.1145/3034786.3034796](https://doi.org/10.1145/3034786.3034796)
