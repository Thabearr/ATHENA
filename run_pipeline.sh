#!/bin/bash
cd /home/thabearr/ATHENA
source .venv/bin/activate
python3 -m workers.fotmob_loader
python3 run_analysis.py
