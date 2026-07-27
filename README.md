<p align="center">
  <img src="docs/athena_banner.png" alt="ATHENA" width="600"/>
</p>

<h1 align="center">ATHENA</h1>
<h3 align="center">Fullproof Strategy Engine for Football Accumulator Prediction</h3>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12+-blue?logo=python&logoColor=white" alt="Python"/>
  <img src="https://img.shields.io/badge/ML-scikit--learn-orange?logo=scikit-learn&logoColor=white" alt="scikit-learn"/>
  <img src="https://img.shields.io/badge/Data-FotMob%20%7C%20OpenFootball-green" alt="Data Sources"/>
  <img src="https://img.shields.io/badge/License-Proprietary-red" alt="License"/>
  <img src="https://img.shields.io/badge/Status-Active%20Development-brightgreen" alt="Status"/>
</p>

---

> **⚠️ PROPRIETARY SOFTWARE** — This repository and all its contents are protected under a proprietary license. Unauthorized copying, distribution, or use is strictly prohibited. See [LICENSE](LICENSE) for details.

---

## 🧠 What Is ATHENA?

**ATHENA** is an AI-powered football prediction engine that generates high-confidence accumulator betting slips by analysing thousands of data points across dozens of leagues worldwide.

Unlike simple odds-comparison tools, ATHENA runs a **multi-engine intelligence pipeline** that combines statistical modelling, machine learning, and real-time data enrichment to identify edges that the market undervalues.

### Key Capabilities

- **10,000+ Historical Matches** seeded from 25+ leagues across Europe, South America, Africa, and Asia
- **Reasoning-Based Fixture Selection (`fixture_reasoner.py`)** — Shin's (1993) de-vigging method, Wilson score confidence discounting, percentage point edge ranking (\(\text{edge}_{\text{pp}}\)), and fractional Kelly bankroll sizing (\(\frac{1}{8}\) Kelly)
- **Dual Prediction Engine (`prediction_engine.py`)** — Fuses Base-Rate pattern memory (System 1) with Bounded Contextual LLM Research Overlay (System 2) in logit space with source-tier fact weighting (`official`: 1.0, `reported`: 0.6, `rumor`: 0.25)
- **Market Coherence & Uncertainty Feedback** — Renormalizes mutually exclusive markets to 1.0 and discounts effective sample size (\(n_{\text{effective}}\)) when fresh news nudges base rates
- **Strict Gender & Women's Match Safety Filter (`services/gender_filter.py`)** — Multi-lingual regex service guaranteeing 100% men's-only accumulator selection
- **Live NLP Context Engine** using real-time Google Search data to gauge team fatigue, pressure, and motivation based on current news cycles
- **ELO Rating System** with chronological backfill — every match is rated using only data available *before* kick-off
- **Expected Goals (xG) & Possession** scraped from FotMob's live API via anti-detection bypass
- **Random Forest ML Models** trained on rolling 5-match team form, xG differentials, and ELO gaps
- **Auditable Desktop UI & Selenium E2E Suite** powered by FastAPI, Pywebview, Vanilla JS with live audit traces, and Edge WebDriver automation

---

## 🏗️ Architecture

```
ATHENA/
├── build_acca.py              # CLI entry point — generates daily acca slips
├── intelligence/
│   ├── fixture_reasoner.py    # Shin de-vigging, Wilson CI, single market selection, correlation flags
│   ├── prediction_engine.py   # Dual-Engine: Base-rate + Logit contextual overlay + uncertainty discount
│   ├── match_analyst.py       # Master prediction engine (Poisson + ML + Reasoner blend)
│   ├── ml_engine.py           # scikit-learn model loader and predictor
│   ├── elo_engine.py          # Dynamic ELO rating system
│   ├── accumulator.py         # Multi-fold accumulator builder
│   ├── acca_filter.py         # Edge & confidence filters
│   ├── correlation_analyzer.py# Cross-match correlation detection
│   ├── h2h_analyzer.py        # Head-to-head historical analysis
│   ├── form.py                # Team form scoring
│   ├── fatigue.py             # Match congestion & fatigue modelling
│   ├── motivation.py          # Seasonal motivation signals
│   ├── weather.py             # Weather impact analysis
│   ├── injuries.py            # Squad availability engine
│   ├── referee.py             # Referee volatility profiling
│   ├── venue_adjuster.py      # Home advantage calibration
│   └── league_adjuster.py     # Cross-league strength normalisation
├── engine/
│   ├── risk_engine.py         # Risk scoring and upset detection
│   └── kelly_criterion.py     # Optimal stake calculation
├── workers/
│   ├── fotmob_scraper.py      # FotMob fixture scraper
│   ├── fotmob_advanced_scraper.py  # Deep stats extraction (xG, lineups, form)
│   └── openfootball_loader.py # OpenFootball historical data loader
├── services/
│   ├── gender_filter.py       # Multi-lingual regex gender & women's match filter
│   ├── analysis_pipeline.py   # Orchestrates the full analysis flow
│   ├── team_form_service.py   # Rolling form calculations
│   ├── prediction_tracker.py  # Tracks prediction accuracy over time
│   └── nlp_engine.py          # Google search and NLP context scoring
├── api/
│   └── server.py              # FastAPI backend for the Desktop UI
├── ui/
│   ├── app.js                 # Frontend logic for accumulator building
│   ├── index.html             # Main desktop UI layout
│   └── styles.css             # UI styling
├── run_desktop.py             # Desktop entry point (Pywebview + FastAPI)
├── database/
│   ├── schema.sql             # Full database schema
│   ├── database.py            # SQLite connection manager
│   └── athena.db              # Local database (10,000+ matches)
├── tools/
│   ├── train_model.py         # ML model training pipeline
│   ├── backtester.py          # Historical prediction backtesting
│   └── model_improver.py      # Model performance analysis
├── models/
│   ├── outcome_model.joblib   # Trained match outcome classifier
│   └── goals_model.joblib     # Trained total goals regressor
├── scripts/
│   ├── backfill_xg.py         # Historical xG data enrichment
│   └── send_email.py          # HTML email notification sender
├── .github/workflows/
│   └── daily_acca.yml         # GitHub Actions daily automation
└── config/
    └── settings.yaml          # Configurable thresholds and parameters
```

---

## ⚡ Quick Start

### Prerequisites

- Python 3.12+
- pip / venv

### Installation

```bash
git clone <your-private-repo-url>
cd ATHENA
```

**For Windows:**
```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -e .
```

**For Linux / macOS (or WSL):**
```bash
python3 -m venv .venv_linux
source .venv_linux/bin/activate
pip install -e .
```

### Seed the Database

```bash
python seed_historical_matches.py    # Fetch 10,000+ historical matches
python scripts/backfill_xg.py       # Enrich with xG & possession from FotMob
```

### Train the ML Models

```bash
python tools/train_model.py
```

### Run the Desktop Interface

The easiest way to generate accumulators and interact with the engine is via the new Desktop UI:

```bash
python run_desktop.py
```

Desktop notes:
- Fixture and league responses are cached server-side for faster repeated navigation.
- Athenizer now supports **Optimize**, **Split**, and **Merge** booking-code workflows.
- Navigation keyboard shortcuts are available with `Alt+1..5`.

### Generate Accumulators via CLI

You can also run the engine entirely from the terminal:

```bash
# Just today's matches, 20 folds
python build_acca.py --days 1 --folds 20 --no-strict

# Target a specific league, 5 folds
python build_acca.py --days 2 --folds 5 --league "Premier League"
```

---

## 🔬 How It Works

### 1. Data Collection
ATHENA scrapes live fixture data from **FotMob** using `curl_cffi` with browser impersonation to bypass anti-bot protections, and seeds historical data from **OpenFootball's** open datasets.

### 2. Feature Engineering
For each upcoming match, ATHENA computes:
- **ELO Differential** — the rating gap between teams based on 10,000+ chronologically-ordered results
- **Rolling 5-Match xG** — each team's expected goals average over their last 5 games
- **Possession Trends** — ball dominance patterns
- **Form Score** — recent W/D/L weighted by opponent strength
- **Fatigue Index** — days since last match, fixture congestion
- **Motivation Signal** — title race, relegation battle, dead rubber detection
- **Weather Impact** — temperature and conditions affecting play style
- **Referee Profile** — card/penalty tendencies of the assigned official

### 3. Prediction Engine
Two models run in parallel and their outputs are blended:

| Engine | Method | Strength |
|--------|--------|----------|
| **Poisson Model** | Mathematical distribution | Excellent at baseline goal probabilities |
| **Random Forest** | ML trained on 4,600+ matches | Captures non-linear xG/ELO/fatigue interactions |

The final probability for each market (1X2, Over/Under, BTTS, etc.) is a **50/50 blend** of both engines.

### 4. Accumulator Construction
The `AccumulatorBuilder` selects bets with:
- Minimum **edge differential** (predicted probability vs. implied odds probability)
- **Correlation filtering** to avoid same-league stacking
- **Risk scoring** with upset alerts for volatile fixtures
- **Market diversity** to spread across 1X2, Over 1.5, BTTS, etc.

---

## 📊 Model Performance

| Metric | Value |
|--------|-------|
| Training Samples | 4,632 matches |
| Outcome Accuracy (1X2) | 48.3% |
| Home Win Recall | 80% |
| Total Goals MSE | 2.64 |
| Leagues Covered | 25+ |
| Historical Matches | 10,644 |

> **Note:** 48% raw 1X2 accuracy is strong — the random baseline is 33%. Combined with edge filtering and accumulator construction, this translates to consistent positive expected value.

---

## 🤖 Automation

ATHENA runs daily via **GitHub Actions**:

- **Schedule:** 7:00 AM UTC every day
- **Output:** Generates acca slip → sends styled HTML email
- **Manual Trigger:** Available via `workflow_dispatch`

Configure secrets in your GitHub repo:
- `GMAIL_ADDRESS`
- `GMAIL_APP_PASSWORD`
- `RECIPIENT_EMAIL`

---

## 🔒 Security & Intellectual Property

This project is protected under a **proprietary license**. See [LICENSE](LICENSE).

- All source code, algorithms, and trained models are © the original author
- Git commit history serves as timestamped proof of authorship
- Unauthorized reproduction or distribution will be prosecuted

---

## 🛣️ Roadmap

- [x] Phase 1: Core Architecture & Database
- [x] Phase 2: Multi-Engine Intelligence Pipeline
- [x] Phase 3: Poisson Probability Engine
- [x] Phase 4: FotMob Live Data Integration
- [x] Phase 5: ELO System & Backtesting Framework
- [x] Phase 6: Machine Learning (Random Forest) & xG Integration
- [x] Phase 7: Live Dashboard (Desktop Web UI)
- [x] Phase 8: NLP Live Context Engine (Google Search Sentiment)
- [x] Phase 9: Reasoning-Based Selection & Shin (1993) De-vigging (`fixture_reasoner.py`)
- [x] Phase 10: Dual Prediction Engine & Logit Contextual Overlay (`prediction_engine.py`)
- [x] Phase 11: Multi-Lingual Gender & Women's Match Safety Filter (`gender_filter.py`)
- [x] Phase 12: Selenium E2E Automation & Desktop UI Audit Traces
- [ ] Phase 13: Automated Betting API Integration
- [ ] Phase 14: Telegram/Discord Bot for Alerts

---

<p align="center">
  <b>Built with precision. Powered by data. Protected by law.</b>
</p>
