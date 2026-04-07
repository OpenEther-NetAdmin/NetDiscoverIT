# Multi-Vendor Containerlab + LLM Parsing Benchmark — Design Spec

## Goal

Deploy a mixed Nokia SR Linux + Arista cEOS Containerlab topology to validate and benchmark the full normalization stack (TextFSM, Ollama, Claude, Gemini) against real device output. Nokia SR Linux intentionally has no TextFSM template — it exercises the LLM fallback path. Arista cEOS has full ntc-templates coverage — it exercises the TextFSM path and provides automatically-derived ground truth for LLM scoring.

---

## Topology

File: `infra/gcp/clab/topology-mixed.yml`

```
spine1 (Nokia SR Linux 24.10.1) ─── leaf1 (Arista cEOS, user-downloaded version e.g. 4.32.0F)
spine1                          ─── leaf2 (Arista cEOS, same image)
spine2 (Nokia SR Linux 24.10.1) ─── leaf1
spine2                          ─── leaf2
                                    leaf1 ─── server1 (alpine)
```

**Node roles:**
- `spine1`, `spine2` — Nokia SR Linux. No TextFSM template → all normalization goes through LLM providers. Ground truth from manually-authored golden fixture files.
- `leaf1`, `leaf2` — Arista cEOS. ntc-templates support → TextFSM runs first. TextFSM output becomes ground truth for scoring LLM providers against.
- `server1` — Alpine Linux. Not collected, exists only to give leaf1 an active access port for realistic topology.

**Why mixed?** Cross-vendor LLDP (Nokia spine sees Arista leaf as neighbor and vice versa) validates the topology discovery path across vendors in a single run. This cannot be tested with single-vendor topologies.

**Original `topology.yml`** (Nokia-only) is kept as a fallback for deployments where the Arista image is not yet available.

---

## Benchmark Architecture

### File Layout

```
scripts/
  run_benchmark.py              ← CLI entry point
  benchmark/
    __init__.py
    runner.py                   ← BenchmarkRunner: collection + orchestration
    scorer.py                   ← Scorer: field coverage + accuracy
    providers/
      __init__.py
      base.py                   ← Provider ABC
      ollama.py                 ← OllamaProvider
      claude.py                 ← ClaudeProvider
      gemini.py                 ← GeminiProvider
results/
  .gitignore                    ← ignore results/ except baseline/
  baseline/                     ← manually-promoted reference runs (committed)
tests/benchmark/
  fixtures/
    spine1.json                 ← Nokia golden fixture
    spine2.json                 ← Nokia golden fixture
```

### Provider Interface (`base.py`)

```python
class Provider(ABC):
    name: str  # format: "provider:model" e.g. "ollama:llama3.2:3b"

    @abstractmethod
    async def normalize(self, raw_output: str, vendor: str) -> dict:
        """Run normalization and return structured metadata dict."""
        ...
```

Each provider receives the same raw SSH output string collected once per device. Providers run concurrently per device via `asyncio.gather`.

**Adding a new model** requires only a new class inheriting `Provider`. The runner discovers providers from the `--providers` CLI flag — `ollama:phi3.5` instantiates `OllamaProvider(model="phi3.5")` with no runner changes.

### Runner Flow (`runner.py`)

For each device in the agent config:
1. SSH collect raw output (once, shared across all providers)
2. Concurrently run all providers against that raw output
3. Score each result against ground truth
4. Aggregate into result record

### CLI (`run_benchmark.py`)

```bash
python scripts/run_benchmark.py \
  --providers ollama:llama3.2:3b,claude:claude-sonnet-4-6,gemini:gemini-2.0-pro \
  --devices spine1,leaf1 \
  --config configs/agent-clab-local.yaml \
  --out results/
```

All flags optional — defaults to all providers configured via env vars, all devices in config, `results/` output dir.

---

## Ground Truth

### Arista (automatic TextFSM baseline)

The runner normalizes each Arista device through the TextFSM path before running LLM providers. That structured output becomes the ground truth for that run. No manual authoring required. Ground truth stays current as device state changes (e.g., interface additions).

### Nokia (golden fixtures)

Manually-authored JSON files at `tests/benchmark/fixtures/{hostname}.json`. Authored once after first `clab-up` by SSHing into the device and inspecting actual output.

**Fixture schema:**
```json
{
  "device": "spine1",
  "vendor": "nokia",
  "ground_truth_source": "fixture",
  "required_fields": {
    "hostname": "spine1",
    "sw_version": "v24.10.1",
    "chassis_type": "7220 IXR-D2L"
  },
  "required_lists": {
    "interfaces": {
      "min_count": 3,
      "must_contain": [{"name": "mgmt0"}, {"name": "ethernet-1/1"}]
    },
    "lldp_neighbors": {
      "min_count": 2,
      "must_contain": [{"hostname": "leaf1"}, {"hostname": "leaf2"}]
    }
  }
}
```

### Scoring (`scorer.py`)

Per provider per device:
- `field_coverage` — % of `required_fields` keys present in provider output
- `field_accuracy` — % of present fields whose values match expected values
- `list_coverage` — % of `required_lists` entries satisfied
- `overall` — weighted average (0.4 × field_coverage + 0.4 × field_accuracy + 0.2 × list_coverage)

---

## Results Format

**File:** `results/benchmark-YYYY-MM-DD-HH-MM.json`

```json
{
  "run_id": "2026-04-05-14-32",
  "topology": "mixed",
  "providers": ["ollama:llama3.2:3b", "claude:claude-sonnet-4-6"],
  "devices": [
    {
      "hostname": "spine1",
      "vendor": "nokia",
      "ground_truth_source": "fixture",
      "results": {
        "ollama:llama3.2:3b": {
          "field_coverage": 0.87,
          "field_accuracy": 0.94,
          "list_coverage": 0.75,
          "overall": 0.85,
          "latency_sec": 42.3,
          "normalized_output": {}
        },
        "claude:claude-sonnet-4-6": {
          "field_coverage": 1.0,
          "field_accuracy": 0.98,
          "list_coverage": 1.0,
          "overall": 0.99,
          "latency_sec": 3.1,
          "normalized_output": {}
        }
      }
    }
  ],
  "summary": {
    "ollama:llama3.2:3b":       {"mean_overall": 0.81, "mean_latency_sec": 45.2},
    "claude:claude-sonnet-4-6": {"mean_overall": 0.97, "mean_latency_sec": 3.4}
  }
}
```

**Stdout during run:**
```
Device    Provider                  Coverage  Accuracy  Latency
spine1    ollama:llama3.2:3b        87%       94%       42s
spine1    claude:claude-sonnet-4-6  100%      98%       3s
leaf1     textfsm (baseline)        100%      —         0.1s
leaf1     ollama:llama3.2:3b        91%       88%       38s
leaf1     claude:claude-sonnet-4-6  100%      97%       2.8s

Results saved to results/benchmark-2026-04-05-14-32.json
```

**Baseline promotion:** Copy any result file to `results/baseline/` and commit. This creates a committed reference point for comparing future runs.

---

## GCP Changes

### 1. `infra/gcp/variables.tf` — VM size

`cloud_machine_type` default changes from `e2-standard-4` (4 vCPU, 16GB) to `e2-highmem-4` (4 vCPU, 32GB, ~$0.13/hr). Required to run all docker-compose services simultaneously with `llama3.2:3b` loaded in RAM. No GPU quota needed — Ollama falls back to CPU automatically.

### 2. `infra/gcp/scripts/cloud-startup.sh` — Ollama model pull

After `docker compose up -d ...`:
```bash
echo "Pulling Ollama model for CPU inference (no GPU required)..."
docker exec netdiscoverit-ollama ollama pull llama3.2:3b
```

### 3. Makefile — `gcp-push-ceos` target

Run once before `make gcp-up` to push the locally-imported cEOS image to GCP Artifact Registry:

```makefile
gcp-push-ceos:
    gcloud artifacts repositories create netdiscoverit \
        --repository-format=docker --location=$(GCP_REGION) || true
    docker tag $(CEOS_IMAGE) $(GCP_REGION)-docker.pkg.dev/$(GCP_PROJECT)/netdiscoverit/ceos:latest
    docker push $(GCP_REGION)-docker.pkg.dev/$(GCP_PROJECT)/netdiscoverit/ceos:latest
```

Variables: `GCP_REGION ?= us-central1`, `CEOS_IMAGE ?= ceos:4.32.0F`

### 4. `infra/gcp/scripts/agent-startup.sh` — pull cEOS from registry

Before `containerlab deploy`:
```bash
gcloud auth configure-docker ${REGION}-docker.pkg.dev --quiet
docker pull ${REGION}-docker.pkg.dev/${PROJECT_ID}/netdiscoverit/ceos:latest
docker tag  ${REGION}-docker.pkg.dev/${PROJECT_ID}/netdiscoverit/ceos:latest ceos:4.32.0F
```

### First GCP deploy workflow

```bash
# 1. Import cEOS from arista.com download
docker import cEOS64-lab-4.32.0F.tar.xz ceos:4.32.0F

# 2. Push to Artifact Registry (one-time)
make gcp-push-ceos

# 3. Provision infrastructure
make gcp-up
```

---

## Makefile Targets

| Target | Action |
|--------|--------|
| `make benchmark` | Run all providers against all devices, write results JSON |
| `make benchmark PROVIDERS=ollama:llama3.2:3b` | Run specific provider only |
| `make benchmark DEVICES=spine1,leaf1` | Run against subset of devices |
| `make clab-up-mixed` | Deploy mixed Nokia+Arista topology |
| `make clab-up` | Deploy Nokia-only topology (fallback, no cEOS needed) |
| `make clab-down` | Destroy whichever topology is running |
| `make gcp-push-ceos` | Push cEOS image to GCP Artifact Registry |

---

## What Is Not In Scope

- Grafana/dashboard for benchmark results (JSON files are sufficient for now)
- SNMP collection from SR Linux or cEOS (SSH is sufficient for current metadata schema)
- Arista cEOS image building or automation of arista.com download (requires human login)
- CI benchmark runs (Containerlab requires privileged Docker, not supported on standard GitHub Actions runners)
- Scoring against a previously-promoted baseline automatically (manual comparison for now)
