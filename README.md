<h1 align="center">ATHENA</h1>

<p align="center">
  <strong>Evidence-driven football intelligence and decision-support research system.</strong><br/>
  Turning information overload into auditable, reproducible decisions.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white" alt="Python 3.12+"/>
  <img src="https://img.shields.io/badge/Research-Shadow%20Mode-5B5BD6" alt="Research / Shadow Mode"/>
  <img src="https://img.shields.io/badge/CI-GitHub%20Actions-2088FF?logo=githubactions&logoColor=white" alt="GitHub Actions"/>
  <img src="https://img.shields.io/badge/License-Proprietary-B91C1C" alt="Proprietary License"/>
</p>

> **Current boundary:** ATHENA is under active research and Shadow validation. Production wagering authority is deliberately disabled. A valid outcome can be **NO BET** when the evidence does not justify a selection.

## The problem ATHENA is solving

Modern football analysis is increasingly an **information-overload problem**.

Before kickoff, useful evidence can span historical results, expected goals, team strength, tactical context, availability, schedule load, competition stage, live fixture state, bookmaker market semantics, quote freshness, settlement rules, and source-specific identifiers. Across many fixtures and markets, there is simply **more relevant data to process, reconcile, and keep fresh than a human can realistically track with consistent accuracy and provenance**.

ATHENA is being built to make that problem tractable.

The system collects and reconciles source evidence, preserves where each fact came from, converts qualified information into model features, evaluates supported football markets, checks current prices and settlement semantics, and produces a traceable decision. Its objective is not to manufacture a pick for every match; it is to surface the most defensible opportunity **only when the complete evidence chain supports one**.

In practical terms, ATHENA aims to inspect a fixture more thoroughly, consistently, and recently than an unaided person can — and to explain why it selected an opportunity or why it refused the fixture.

## Design philosophy

ATHENA is built around a small set of non-negotiable engineering principles:

| Principle | What it means in ATHENA |
| --- | --- |
| **Evidence before inference** | Important facts retain source lineage, observation time, and evidence identity. Missing evidence is not invented to complete a pipeline. |
| **Fail closed** | Unknown, stale, malformed, conflicted, or unverified state blocks authority instead of being silently guessed. |
| **Time-aware modelling** | Historical features and evaluation are constructed as-of the information that existed before the target kickoff. |
| **Exact identity** | Reviewed provider paths use deterministic fixture, market, outcome, line, snapshot, and hash identities rather than convenient fuzzy matches. |
| **Market coherence** | Related markets are derived from coherent probability/settlement semantics instead of being treated as unrelated labels. |
| **Price discipline** | Football probability and bookmaker value are separate questions. Quote freshness, source consistency, and settlement semantics remain explicit. |
| **Reproducibility** | Canonical serialization, SHA-256 identities, deterministic ordering, immutable inputs, and replayable artifacts are used throughout reviewed boundaries. |
| **Abstention is valid** | `NO_BET`, `MISSING`, `BLOCKED`, `STALE`, and `CONFLICTED` are meaningful outcomes — not errors to hide. |

## What ATHENA does

ATHENA combines data engineering, statistical modelling, machine learning, provider reconciliation, and decision governance in one auditable workflow.

### Evidence and football-state layer

- Builds and audits historical football evidence for model research and backtesting.
- Preserves raw/source lineage and deterministic identities across reviewed evidence boundaries.
- Reconciles current fixtures across source systems instead of assuming names or IDs are globally interchangeable.
- Represents fixture intelligence such as form, performance, schedule load, availability, lineup/context, venue, weather, and competition state without allowing discovery-only information to silently become trusted evidence.
- Keeps missingness, conflicts, freshness, and uncertainty explicit.

### Probability and market layer

- Uses a shared score/goal-distribution foundation for markets that can be derived coherently from the same football state.
- Supports specialist treatment where settlement or match-path semantics require different information.
- Maintains a canonical **15-market** analytical surface rather than building one disconnected model per bookmaker option.
- Preserves settlement-aware logic for ordinary event markets and non-binary structures such as **Draw No Bet** and **Asian Handicap**.
- Keeps probability quality, calibration, bookmaker pricing, and portfolio behaviour as separate research questions.

### Current-price and routing layer

- Replays reviewed current-source context before market evaluation.
- Maps provider events, markets, outcomes, lines, and quotes through exact source identities.
- Enforces explicit freshness and currentness gates before a quote is considered usable.
- Prices the complete eligible audit surface before routing, preserving rejected and unpriced opportunities for analysis.
- Uses deterministic ranking and retains counterfactual/diagnostic information so a final selection can be reproduced and inspected.

### Research and validation layer

- Uses chronological and rolling-origin evaluation rather than random future-leaking splits for time-dependent research.
- Runs heavy validation and reproducibility checks through GitHub-hosted workflows so the local machine is not the critical path.
- Treats new models, features, routers, and policies as challengers that must earn authority through frozen evidence rather than complexity alone.
- Keeps Shadow results separate from production authority.

## Architecture

```text
Historical + current source evidence
                |
                v
       Raw evidence + provenance
                |
                v
      Source / schema qualification
                |
                v
     Fixture identity + reconciliation
                |
                v
        Fixture intelligence state
                |
                v
      Verified model-feature snapshot
                |
                v
   Probability models + calibration research
                |
                v
    15-market probability / settlement layer
                |
                v
   Exact current provider quote reconciliation
                |
                v
        Price-all audit + diagnostics
                |
                v
        Deterministic Shadow router
                |
                v
     Candidate / NO BET + audit trail
```

Each layer is deliberately separated so that trust cannot jump directly from raw data to a betting decision.

## Engineering highlights

- **Provenance-first data contracts** with deterministic hashes and source ancestry.
- **Strict schema validation** with explicit rejection of malformed or semantically ambiguous inputs.
- **Cross-source fixture reconciliation** and current-provider semantic registries.
- **Chronological historical replay** for leakage-resistant feature and model research.
- **Normalized score-distribution modelling** for coherent result/goal market probabilities.
- **Settlement-aware evaluation** for push and split-settlement markets.
- **Freshness-aware current quote handling** with exact snapshot identity.
- **Shadow-first deployment discipline**: research success does not automatically become production authority.
- **Hosted CI and research workflows** for repeatable tests, audits, evidence campaigns, and large backtests.
- **Auditable UI/API tooling** for inspecting the system rather than hiding its reasoning behind a single score.

## Technology

| Area | Stack |
| --- | --- |
| Core | Python 3.12+ |
| Data | SQLite, SQLAlchemy, pandas, NumPy, PyArrow |
| Modelling | SciPy, scikit-learn, joblib |
| Validation | Pydantic, pytest, deterministic JSON/hash contracts |
| API / UI | FastAPI, Uvicorn, Pywebview, JavaScript |
| Acquisition / parsing | HTTPX, aiohttp, requests, BeautifulSoup, lxml |
| Automation | GitHub Actions |
| Research outputs | JSON, CSV, SQLite, Markdown, reproducible artifacts |

## Repository guide

```text
ATHENA/
├── domain/              # Canonical contracts, market semantics and reviewed boundaries
├── intelligence/        # Football analysis, probability and contextual intelligence
├── engine/              # Risk / decision-support engines
├── workers/             # Source acquisition and ingestion workers
├── services/            # Application and analysis services
├── database/            # Local persistence and schema layer
├── api/                 # FastAPI application surface
├── ui/                  # Desktop/web interface assets
├── tools/               # Training, backtesting and research utilities
├── scripts/             # Audits, migrations, evidence and operational helpers
├── docs/                # Architecture decisions, contracts and current-state documentation
├── tests/               # Unit, integration, replay and adversarial regression tests
└── .github/workflows/   # Hosted CI, research, acquisition and validation workflows
```

ATHENA has evolved through narrow, reviewable boundaries. The `docs/` directory records the contracts and rationale behind those boundaries; the code and exact current Git state remain authoritative for implementation.

## Development environment

ATHENA is primarily developed against Python 3.12+.

From an **authorized local checkout**:

```bash
python -m venv .venv
```

Activate the environment for your platform, then install the repository dependencies:

```bash
pip install -r requirements.txt
```

ATHENA's normal engineering workflow favors **targeted local tests and compile/syntax checks**, with the complete repository validation delegated to GitHub-hosted CI. Source-acquisition and evidence workflows may have additional authorization and provenance requirements; do not run them casually from a development checkout.

## Project status

ATHENA is an active research project, not a finished commercial betting product.

The current engineering direction is focused on:

1. hardening the end-to-end all-market Shadow path;
2. proving deterministic current-source, pricing, routing, and portfolio behaviour with real preserved evidence;
3. expanding hosted chronological backtesting and champion/challenger evaluation;
4. improving tactical, availability, lineup, regime, and uncertainty features where historical evidence supports them;
5. validating model and routing changes on frozen holdouts and prospective Shadow observations before any increase in authority.

The project deliberately does **not** treat a green test suite, a high historical hit rate, or a successful field trial as sufficient evidence for production deployment.

## License and intellectual property

ATHENA is **proprietary software**. Public visibility of this repository does **not** make it open source and does not grant permission to copy, redistribute, modify, sublicense, reverse engineer, create derivative works from, or commercially use the project.

The repository's [LICENSE](LICENSE) applies to the source code, documentation, algorithms, trained models, database schemas, analytical methodologies, proprietary datasets, and generated analytical outputs. Separate written permission or a commercial license is required where specified by that license.

Copyright © 2025–2026 ATHENA Project. All Rights Reserved.

## Disclaimer

ATHENA is a research and decision-support system for probabilistic football analysis. Football outcomes remain uncertain. The project does not guarantee profit, does not claim certainty, and is intentionally designed to refuse unsupported decisions. The software is provided subject to the warranty and liability terms in the repository's proprietary license.

---

<p align="center">
  <strong>ATHENA — evidence in, uncertainty preserved, decisions earned.</strong>
</p>
