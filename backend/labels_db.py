"""
SQLite database for label storage.

Replaces JSON file storage with efficient indexed database.
Database location: ~/blore_data/labels.db
"""

import sqlite3
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)

DB_PATH = Path.home() / 'blore_data' / 'labels.db'


def init_db():
    """Create tables if they don't exist."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS labels (
            id TEXT PRIMARY KEY,
            viewport_name TEXT NOT NULL,
            name TEXT NOT NULL,
            color TEXT,
            threshold REAL,
            source_lat REAL,
            source_lon REAL,
            pixel_count INTEGER,
            created TEXT,
            visible INTEGER DEFAULT 1
        );

        CREATE INDEX IF NOT EXISTS idx_labels_viewport ON labels(viewport_name);

        CREATE TABLE IF NOT EXISTS label_pixels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label_id TEXT NOT NULL,
            lat REAL NOT NULL,
            lon REAL NOT NULL,
            distance REAL,
            FOREIGN KEY (label_id) REFERENCES labels(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_pixels_label ON label_pixels(label_id);
    ''')
    conn.commit()
    conn.close()
    logger.info(f"Labels database initialized: {DB_PATH}")


@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Dict-like access
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def get_labels(viewport_name: str) -> list:
    """Get all labels for a viewport with their pixels."""
    with get_db() as conn:
        labels = conn.execute(
            "SELECT * FROM labels WHERE viewport_name = ? ORDER BY created",
            (viewport_name,)
        ).fetchall()

        result = []
        for label in labels:
            pixels = conn.execute(
                "SELECT lat, lon, distance FROM label_pixels WHERE label_id = ?",
                (label['id'],)
            ).fetchall()

            label_dict = dict(label)
            label_dict['pixels'] = [dict(p) for p in pixels]
            label_dict['visible'] = bool(label_dict.get('visible', 1))

            # Reconstruct source_pixel dict
            if label_dict.get('source_lat') is not None:
                label_dict['source_pixel'] = {
                    'lat': label_dict.pop('source_lat'),
                    'lon': label_dict.pop('source_lon')
                }
            else:
                label_dict.pop('source_lat', None)
                label_dict.pop('source_lon', None)

            result.append(label_dict)

        return result


def save_label(viewport_name: str, label_data: dict) -> str:
    """Save a new label with pixels. Returns label_id."""
    label_id = label_data.get('id') or f"label_{int(datetime.utcnow().timestamp() * 1000)}"
    created = label_data.get('created') or datetime.utcnow().isoformat() + 'Z'
    pixels = label_data.get('pixels', [])
    source_pixel = label_data.get('source_pixel', {})

    with get_db() as conn:
        # Insert label
        conn.execute('''
            INSERT INTO labels (id, viewport_name, name, color, threshold,
                               source_lat, source_lon, pixel_count, created, visible)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            label_id,
            viewport_name,
            label_data.get('name', 'Unnamed'),
            label_data.get('color', '#888888'),
            label_data.get('threshold'),
            source_pixel.get('lat'),
            source_pixel.get('lon'),
            len(pixels),
            created,
            1 if label_data.get('visible', True) else 0
        ))

        # Batch insert pixels (efficient)
        if pixels:
            conn.executemany(
                "INSERT INTO label_pixels (label_id, lat, lon, distance) VALUES (?, ?, ?, ?)",
                [(label_id, p['lat'], p['lon'], p.get('distance')) for p in pixels]
            )

        conn.commit()
        logger.info(f"Saved label '{label_data.get('name')}' with {len(pixels)} pixels for {viewport_name}")

    return label_id


def delete_label(viewport_name: str, label_id: str) -> bool:
    """Delete a label and its pixels (via CASCADE). Returns True if deleted."""
    with get_db() as conn:
        cursor = conn.execute(
            "DELETE FROM labels WHERE id = ? AND viewport_name = ?",
            (label_id, viewport_name)
        )
        conn.commit()
        deleted = cursor.rowcount > 0

        if deleted:
            logger.info(f"Deleted label '{label_id}' from {viewport_name}")

        return deleted


def update_label_visibility(viewport_name: str, label_id: str, visible: bool) -> bool:
    """Update label visibility. Returns True if updated."""
    with get_db() as conn:
        cursor = conn.execute(
            "UPDATE labels SET visible = ? WHERE id = ? AND viewport_name = ?",
            (1 if visible else 0, label_id, viewport_name)
        )
        conn.commit()
        return cursor.rowcount > 0


def get_label_count(viewport_name: str) -> int:
    """Get count of labels for a viewport."""
    with get_db() as conn:
        result = conn.execute(
            "SELECT COUNT(*) FROM labels WHERE viewport_name = ?",
            (viewport_name,)
        ).fetchone()
        return result[0] if result else 0


def delete_viewport_labels(viewport_name: str) -> int:
    """Delete all labels for a viewport. Returns count deleted."""
    with get_db() as conn:
        # Get label IDs first
        label_ids = [row[0] for row in conn.execute(
            "SELECT id FROM labels WHERE viewport_name = ?",
            (viewport_name,)
        ).fetchall()]

        if label_ids:
            # Explicitly delete pixels (in case CASCADE doesn't work)
            placeholders = ','.join('?' * len(label_ids))
            conn.execute(
                f"DELETE FROM label_pixels WHERE label_id IN ({placeholders})",
                label_ids
            )

        # Delete labels
        cursor = conn.execute(
            "DELETE FROM labels WHERE viewport_name = ?",
            (viewport_name,)
        )
        conn.commit()
        logger.info(f"Deleted {cursor.rowcount} labels for viewport {viewport_name}")
        return cursor.rowcount
