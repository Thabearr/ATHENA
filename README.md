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
- **ELO Rating System** with chronological backfill — every match is rated using only data available *before* kick-off
- **Expected Goals (xG) & Possession** scraped from FotMob's live API via anti-detection bypass
- **Random Forest ML Models** trained on rolling 5-match team form, xG differentials, and ELO gaps
- **Hybrid Poisson-ML Probability Engine** that blends mathematical distributions with learned patterns
- **10+ Analytical Engines** running in parallel: Form, Fatigue, Motivation, Weather, Injuries, Referee, H2H, Venue, League Strength, Correlation
- **Smart Accumulator Builder** with configurable fold count, minimum edge thresholds, and market diversity
- **Risk Assessment System** with upset alerts, stale-data warnings, and confidence scoring
- **Daily Automation** via GitHub Actions with HTML email notifications

---

## 🏗️ Architecture

```
ATHENA/
├── build_acca.py              # CLI entry point — generates daily acca slips
├── intelligence/
│   ├── match_analyst.py       # Master prediction engine (Poisson + ML blend)
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
│   ├── analysis_pipeline.py   # Orchestrates the full analysis flow
│   ├── team_form_service.py   # Rolling form calculations
│   └── prediction_tracker.py  # Tracks prediction accuracy over time
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
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
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

### Generate Today's Accumulator

```bash
python build_acca.py generate --days 2 --folds 10
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
- [ ] Phase 7: Live Dashboard (Web UI)
- [ ] Phase 8: Automated Betting API Integration
- [ ] Phase 9: Telegram/Discord Bot for Alerts
- [ ] Phase 10: Model V2 (XGBoost / Neural Network)

---

<p align="center">
  <b>Built with precision. Powered by data. Protected by law.</b>
</p>
