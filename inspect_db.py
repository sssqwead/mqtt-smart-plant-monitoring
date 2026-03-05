"""Quick utility to inspect recent rows in the SQLite database."""

from __future__ import annotations

import sqlite3
from pathlib import Path

# Path to the database file — must match the value in config.py
DATABASE_PATH = "plant_monitoring.db"


def print_rows(cursor: sqlite3.Cursor, query: str, title: str) -> None:
    """Execute a query and print results with a header and column names."""
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")

    rows = cursor.execute(query).fetchall()

    if not rows:
        print("  (no rows)")
        return

    # Extract column names from the cursor description after executing the query
    col_names = [desc[0] for desc in cursor.description]
    print("  " + "  |  ".join(col_names))
    print("  " + "─" * (len("  |  ".join(col_names)) + 2))

    # Print each row, replacing None values with a dash for readability
    for row in rows:
        print("  " + "  |  ".join(str(v) if v is not None else "–" for v in row))


def main() -> int:
    database_path = Path(DATABASE_PATH)

    # Exit early if the database hasn't been created yet
    if not database_path.exists():
        print(f"Database not found: {database_path}")
        return 1

    with sqlite3.connect(database_path) as connection:
        cursor = connection.cursor()

        # Show the 10 most recent sensor readings including all extended fields
        print_rows(
            cursor,
            """
            SELECT id, timestamp, plant_id, plant_type,
                   soil_moisture, temperature, humidity,
                   nitrogen, phosphorus, potassium,
                   soil_ph, salinity, root_temperature
            FROM sensor_data
            ORDER BY id DESC
            LIMIT 10
            """,
            "Latest Sensor Readings (10 most recent)",
        )

        # Show the 20 most recent activity log entries including severity
        print_rows(
            cursor,
            """
            SELECT id, timestamp, event_type, severity, details
            FROM activity_log
            ORDER BY id DESC
            LIMIT 20
            """,
            "Latest Activity Log (20 most recent)",
        )

        # Summary: how many alerts were published at each severity level
        print_rows(
            cursor,
            """
            SELECT severity, COUNT(*) as count
            FROM activity_log
            WHERE event_type = 'alert_published'
            GROUP BY severity
            ORDER BY count DESC
            """,
            "Alert Summary by Severity",
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
