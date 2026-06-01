"""
Run this ONCE to add the star_rating column to your existing DB.
It will NOT delete any existing reviews.

Usage:
    python migrate.py
"""

import sqlite3
import os

# Path to your DB — adjust if yours is in a different location
DB_PATH = os.path.join(os.path.dirname(__file__), 'instance', 'final_v11.db')

# Fallback: try current directory too
if not os.path.exists(DB_PATH):
    DB_PATH = os.path.join(os.path.dirname(__file__), 'final_v11.db')

if not os.path.exists(DB_PATH):
    print(f"ERROR: Could not find final_v11.db")
    print("Please edit DB_PATH in this script to point to your .db file.")
    exit(1)

print(f"Found DB at: {DB_PATH}")

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Check if column already exists
cursor.execute("PRAGMA table_info(review)")
columns = [row[1] for row in cursor.fetchall()]
print(f"Existing columns: {columns}")

added = []

if 'star_rating' not in columns:
    cursor.execute("ALTER TABLE review ADD COLUMN star_rating INTEGER DEFAULT 5")
    added.append("star_rating (default 5)")

if 'is_verified' not in columns:
    cursor.execute("ALTER TABLE review ADD COLUMN is_verified INTEGER DEFAULT 0")
    added.append("is_verified (default 0 = unverified)")

conn.commit()

if added:
    print(f"SUCCESS: Added columns: {', '.join(added)}")
    print("Existing reviews are unaffected (old reviews = unverified, 5 stars).")
else:
    print("All columns already exist. Nothing to do!")

conn.close()
print("Done! You can now restart your Flask app.")