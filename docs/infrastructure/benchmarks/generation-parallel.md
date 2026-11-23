# Lesson generation concurrency benchmark

Controlled local workload, no network and no paid provider calls.

- 15 independent lesson units (Mathematics, Basic 4, WAPEF-approved template)
- Mock provider latency: 0.25 s per lesson, one provider call per lesson
- Same workload and content for every worker count
- Peak provider calls measured inside the mock transport
- Raw data: `generation-parallel.json`

| Workers | Total | Average lesson | Median lesson | P95 lesson | Peak provider calls | Failures | Duplicates | Speed-up |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 4.117 s | 0.255 s | 0.254 s | 0.258 s | 1 | 0 | 0 | 1.00x |
| 2 | 2.415 s | 0.253 s | 0.253 s | 0.254 s | 2 | 0 | 0 | 1.70x |
| 3 | 1.695 s | 0.254 s | 0.254 s | 0.257 s | 3 | 0 | 0 | 2.43x |
| 4 | 1.405 s | 0.254 s | 0.254 s | 0.259 s | 4 | 0 | 0 | 2.93x |

Stage breakdown (seconds):

| Workers | Allocation | Deterministic build | Provider | Persistence probe |
|---:|---:|---:|---:|---:|
| 1 | 0.010 | 0.284 | 3.822 | 0.014 |
| 2 | 0.002 | 0.387 | 2.023 | 0.014 |
| 3 | 0.002 | 0.415 | 1.276 | 0.014 |
| 4 | 0.002 | 0.382 | 1.019 | 0.014 |

Deterministic engine (AI OFF): 0.370 s for all 15 lessons (0.35 s build).
Provider latency, not the engine, is the dominant cost for Zeli runs.
Deterministic work is CPU-bound, so it stays sequential: parallel threads
would add GIL contention without reducing the 0.37 s build.

Selection note: 4 workers is fastest in a mock benchmark, but the safest
production default is 3, further capped to the existing
`AI_MAX_CONCURRENT_PER_TEACHER=2` while AI spend control is enabled. That
means the effective default in production is 2 simultaneous provider calls.
