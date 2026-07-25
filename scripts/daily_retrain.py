#!/usr/bin/env python3
import sys
import os
import asyncio
import sqlite3
from datetime import datetime, timedelta

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from tools.train_model import train_models

def daily_retrain():
    print("=== ATHENA DAILY RETRAINING LAYER ===")
    yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"Fetching matches for {yesterday}... (Skipped live fetch to preserve DB integrity)")
    
    print("\nTriggering Model Retraining...")
    train_models()
    print("=== RETRAINING COMPLETE ===")

if __name__ == "__main__":
    daily_retrain()
