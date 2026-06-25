# JioPC Session Hibernate — Benchmark Results

Mode: **fake**  ·  Runs per combination: **20**  ·  Save budget: **10000 ms**

| Combination | Apps | Save mean (ms) | Save p95 (ms) | Restore mean (ms) | Success |
|---|---:|---:|---:|---:|---:|
| student | 3 | 0.3 | 0.3 | 0.3 | 100% |
| trader | 3 | 0.3 | 0.4 | 0.3 | 100% |
| developer | 4 | 0.3 | 0.3 | 0.3 | 100% |
| writer | 2 | 0.3 | 0.3 | 0.2 | 100% |
| researcher | 4 | 0.3 | 0.4 | 0.2 | 100% |
| minimal | 1 | 0.3 | 0.3 | 0.2 | 100% |
| heavy | 6 | 0.3 | 0.4 | 0.3 | 100% |
| office | 3 | 0.3 | 0.4 | 0.4 | 100% |
| files-only | 2 | 0.3 | 0.3 | 0.2 | 100% |
| mixed-unsaved | 4 | 0.3 | 0.3 | 0.2 | 100% |

**Worst-case save mean:** 0.3 ms (0.0% of the 10000 ms budget).
**Mean relaunch success rate:** 100%.

> `--fake` mode times the real saver/registry/restore code against stubbed window enumeration and process spawn, isolating the tool's own overhead from app start-up cost. On a real VM the dominant restore cost is the apps' own launch time, not this tool. See methodology.md.
