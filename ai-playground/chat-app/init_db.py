"""
init_db.py
----------
Local-dev helper to verify the database connection and pre-create the
LangGraph checkpoint tables before first startup.

In production / CI, tables are created automatically by checkpointer.setup()
inside graph/builder.py on the first call to build_graph().  You don't need
to run this script unless you want to validate the connection separately.

Usage
-----
    # Make sure .env is configured, then:
    python init_db.py

Environment variables
---------------------
    DB_URI   — full PostgreSQL connection string
               default: postgresql://postgres:password@localhost:5432/ailixir
"""

import os

import psycopg
from dotenv import load_dotenv
from langgraph.checkpoint.postgres import PostgresSaver

load_dotenv()

DB_URI = os.getenv(
    "DB_URI",
    "postgresql://postgres:password@localhost:5432/ailixir",
)

print(f"Connecting to: {DB_URI.split('@')[-1]}")   # log host/db, not credentials

try:
    conn = psycopg.connect(DB_URI)
    print("✅ Database connection OK")

    checkpointer = PostgresSaver(conn)
    checkpointer.setup()   # creates checkpoints + writes tables if absent
    print("✅ LangGraph checkpoint tables ready")

    conn.close()
    print("✅ init_db done — you can now start the API with: uvicorn main:app --reload")

except psycopg.OperationalError as exc:
    print(f"❌ Could not connect to the database: {exc}")
    print("   Check your DB_URI in .env and make sure PostgreSQL is running.")
    raise SystemExit(1) from exc