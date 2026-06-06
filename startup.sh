#!/bin/bash
set -e

# Initialise the database schema (no-op if tables already exist).
python3 app.py init-db

# Add any new columns introduced by upgrades (safe to run on every start).
python3 app.py migrate-db

# Start the application.
python3 app.py