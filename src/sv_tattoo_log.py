"""
sv_tattoo_log.py — Personal tattoo dossier: CRUD for all tattoo entries.

Stores in sv_tattoo_log.json at the project root alongside sv_key_records.json.
An entry can represent:
  - An *encoded* tattoo (cipher string tattooed on skin; links to a Key Record).
  - An *art* tattoo (regular tattoo design, portrait, flash, etc.).

Passwords and encoded strings are NEVER stored here.
sv_key_records.json is the cold-storage crypto layer; this file is the
aesthetic/layout layer. The two are siblings, never parent-child.

Entry schema:
{
  "id":               "a3f2b1c8",           # 8 hex chars
  "name":             "Left forearm spiral", # user label
  "type":             "encoded" | "art",
  "placement":        "forearm_l",           # see PLACEMENTS constant
  "placement_notes":  "",                    # free text, e.g. "outer side"
  "date_done":        "2025-03-15",          # ISO date string, nullable
  "artist_name":      "",
  "studio_name":      "",
  "style":            "",                    # free text: blackwork, geometric, …
  "ink_colors":       [],                    # list of strings
  "status":           "planned",             # see STATUSES constant
  "size_cm":          null,                  # nullable float
  "price":            null,                  # nullable number
  "currency":         "USD",
  "notes":            "",
  "photos":           [],                    # relative paths under vault/tattoo_images/
  "key_record_id":    null,                  # links to sv_key_records.json; encoded type only
  "layout":           null,                  # last-used layout key
  "layout_params":    {},
  "created":          "2025-05-17 14:00",
  "updated":          "2025-05-17 14:00"
}
"""

from __future__ import annotations

import json
import os
import secrets
import time
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Enum constants (returned to the GUI for dropdowns)
# ---------------------------------------------------------------------------

STATUSES: list[str] = [
    'planned', 'design', 'scheduled', 'fresh', 'healing',
    'healed', 'touchup_needed', 'retired',
]

PLACEMENTS: list[dict[str, str]] = [
    # key, label, category
    {'key': 'head',         'label': 'Head',              'cat': 'Head & Neck'},
    {'key': 'forehead',     'label': 'Forehead',          'cat': 'Head & Neck'},
    {'key': 'behind_ear_l', 'label': 'Behind ear (left)', 'cat': 'Head & Neck'},
    {'key': 'behind_ear_r', 'label': 'Behind ear (right)','cat': 'Head & Neck'},
    {'key': 'neck_front',   'label': 'Neck (front)',      'cat': 'Head & Neck'},
    {'key': 'neck_back',    'label': 'Neck (back)',        'cat': 'Head & Neck'},
    {'key': 'neck_side_l',  'label': 'Neck (left side)',  'cat': 'Head & Neck'},
    {'key': 'neck_side_r',  'label': 'Neck (right side)', 'cat': 'Head & Neck'},

    {'key': 'chest_l',      'label': 'Chest (left)',      'cat': 'Torso'},
    {'key': 'chest_r',      'label': 'Chest (right)',     'cat': 'Torso'},
    {'key': 'sternum',      'label': 'Sternum',           'cat': 'Torso'},
    {'key': 'ribs_l',       'label': 'Ribs (left)',       'cat': 'Torso'},
    {'key': 'ribs_r',       'label': 'Ribs (right)',      'cat': 'Torso'},
    {'key': 'abdomen_upper','label': 'Abdomen (upper)',   'cat': 'Torso'},
    {'key': 'abdomen_lower','label': 'Abdomen (lower)',   'cat': 'Torso'},
    {'key': 'back_upper',   'label': 'Back (upper)',      'cat': 'Torso'},
    {'key': 'back_mid',     'label': 'Back (mid)',         'cat': 'Torso'},
    {'key': 'back_lower',   'label': 'Back (lower)',      'cat': 'Torso'},
    {'key': 'spine',        'label': 'Spine',             'cat': 'Torso'},
    {'key': 'hip_l',        'label': 'Hip (left)',        'cat': 'Torso'},
    {'key': 'hip_r',        'label': 'Hip (right)',       'cat': 'Torso'},

    {'key': 'shoulder_l',   'label': 'Shoulder (left)',   'cat': 'Arms'},
    {'key': 'shoulder_r',   'label': 'Shoulder (right)',  'cat': 'Arms'},
    {'key': 'upper_arm_l',  'label': 'Upper arm (left)',  'cat': 'Arms'},
    {'key': 'upper_arm_r',  'label': 'Upper arm (right)', 'cat': 'Arms'},
    {'key': 'inner_arm_l',  'label': 'Inner arm (left)',  'cat': 'Arms'},
    {'key': 'inner_arm_r',  'label': 'Inner arm (right)', 'cat': 'Arms'},
    {'key': 'elbow_l',      'label': 'Elbow (left)',      'cat': 'Arms'},
    {'key': 'elbow_r',      'label': 'Elbow (right)',     'cat': 'Arms'},
    {'key': 'forearm_l',    'label': 'Forearm (left)',    'cat': 'Arms'},
    {'key': 'forearm_r',    'label': 'Forearm (right)',   'cat': 'Arms'},
    {'key': 'wrist_l',      'label': 'Wrist (left)',      'cat': 'Arms'},
    {'key': 'wrist_r',      'label': 'Wrist (right)',     'cat': 'Arms'},
    {'key': 'hand_l',       'label': 'Hand (left)',       'cat': 'Arms'},
    {'key': 'hand_r',       'label': 'Hand (right)',      'cat': 'Arms'},
    {'key': 'fingers_l',    'label': 'Fingers (left)',    'cat': 'Arms'},
    {'key': 'fingers_r',    'label': 'Fingers (right)',   'cat': 'Arms'},

    {'key': 'thigh_l',      'label': 'Thigh (left)',      'cat': 'Legs'},
    {'key': 'thigh_r',      'label': 'Thigh (right)',     'cat': 'Legs'},
    {'key': 'knee_l',       'label': 'Knee (left)',       'cat': 'Legs'},
    {'key': 'knee_r',       'label': 'Knee (right)',      'cat': 'Legs'},
    {'key': 'shin_l',       'label': 'Shin (left)',       'cat': 'Legs'},
    {'key': 'shin_r',       'label': 'Shin (right)',      'cat': 'Legs'},
    {'key': 'calf_l',       'label': 'Calf (left)',       'cat': 'Legs'},
    {'key': 'calf_r',       'label': 'Calf (right)',      'cat': 'Legs'},
    {'key': 'ankle_l',      'label': 'Ankle (left)',      'cat': 'Legs'},
    {'key': 'ankle_r',      'label': 'Ankle (right)',     'cat': 'Legs'},
    {'key': 'foot_l',       'label': 'Foot (left)',       'cat': 'Legs'},
    {'key': 'foot_r',       'label': 'Foot (right)',      'cat': 'Legs'},
    {'key': 'toes_l',       'label': 'Toes (left)',       'cat': 'Legs'},
    {'key': 'toes_r',       'label': 'Toes (right)',      'cat': 'Legs'},
]

_PLACEMENT_KEYS: frozenset[str] = frozenset(p['key'] for p in PLACEMENTS)


# ---------------------------------------------------------------------------
# Storage location
# ---------------------------------------------------------------------------

# Single authoritative root resolver lives in sv_bridge — import it here so
# every storage module agrees on what "project root" means.
from sv_bridge import project_root as _project_root  # noqa: E402


def _log_path() -> Path:
    return _project_root() / 'data' / 'sv_tattoo_log.json'


# ---------------------------------------------------------------------------
# Raw read / write (atomic-safe via write-then-rename not needed on Win
# single-process app, but we keep the pattern consistent with sv_keyrecord.py)
# ---------------------------------------------------------------------------

def _read_log() -> dict[str, Any]:
    p = _log_path()
    if not p.exists():
        return {'version': 1, 'entries': {}}
    try:
        data = json.loads(p.read_text(encoding='utf-8'))
        if 'entries' not in data:
            data['entries'] = {}
        return data
    except Exception:
        return {'version': 1, 'entries': {}}


def _write_log(log: dict[str, Any]) -> None:
    """Atomic write via .tmp + os.replace (see sv_keyrecord._write_store)."""
    p = _log_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + '.tmp')
    tmp.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding='utf-8')
    os.replace(tmp, p)


# ---------------------------------------------------------------------------
# Entry helpers
# ---------------------------------------------------------------------------

def _now_str() -> str:
    return time.strftime('%Y-%m-%d %H:%M', time.localtime())


def _default_entry(entry_id: str) -> dict[str, Any]:
    """Return a blank entry with all required fields."""
    now = _now_str()
    return {
        'id':               entry_id,
        'name':             '',
        'type':             'art',
        'placement':        '',
        'placement_notes':  '',
        'date_done':        None,
        'artist_name':      '',
        'studio_name':      '',
        'style':            '',
        'ink_colors':       [],
        'status':           'planned',
        'size_cm':          None,
        'price':            None,
        'currency':         'USD',
        'notes':            '',
        'photos':           [],
        'key_record_id':    None,
        'layout':           None,
        'layout_params':    {},
        'created':          now,
        'updated':          now,
    }


def _merge_fields(entry: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """
    Merge *params* into *entry*. Only known field names are accepted; unknown
    keys are silently dropped (prevents injection of arbitrary fields).
    """
    allowed = {
        'name', 'type', 'placement', 'placement_notes', 'date_done',
        'artist_name', 'studio_name', 'style', 'ink_colors', 'status',
        'size_cm', 'price', 'currency', 'notes',
        'key_record_id', 'layout', 'layout_params',
    }
    for k, v in params.items():
        if k in allowed:
            entry[k] = v
    # Coerce type
    if entry.get('type') not in ('encoded', 'art'):
        entry['type'] = 'art'
    if entry.get('status') not in STATUSES:
        entry['status'] = 'planned'
    entry['updated'] = _now_str()
    return entry


# ---------------------------------------------------------------------------
# Public CRUD
# ---------------------------------------------------------------------------

def generate_id() -> str:
    """Return a fresh 8-hex-char unique entry ID."""
    return secrets.token_hex(4)


def create_entry(params: dict[str, Any]) -> dict[str, Any]:
    """Create a new entry, persist it, and return the saved entry."""
    log = _read_log()
    entry_id = generate_id()
    # Ensure ID is unique (birthday collision is negligible at this scale)
    while entry_id in log['entries']:
        entry_id = generate_id()
    entry = _default_entry(entry_id)
    entry = _merge_fields(entry, params)
    log['entries'][entry_id] = entry
    _write_log(log)
    return entry


def get_entry(entry_id: str) -> dict[str, Any] | None:
    """Return the entry dict or None if not found."""
    log = _read_log()
    return log['entries'].get(entry_id)


def list_entries() -> list[dict[str, Any]]:
    """Return all entries sorted by created desc."""
    log = _read_log()
    entries = list(log['entries'].values())
    entries.sort(key=lambda e: e.get('created', ''), reverse=True)
    return entries


def update_entry(entry_id: str, params: dict[str, Any]) -> dict[str, Any] | None:
    """Update fields in an existing entry. Returns updated entry or None."""
    log = _read_log()
    entry = log['entries'].get(entry_id)
    if entry is None:
        return None
    entry = _merge_fields(entry, params)
    log['entries'][entry_id] = entry
    _write_log(log)
    return entry


def delete_entry(entry_id: str) -> tuple[bool, str | None]:
    """
    Delete an entry. Returns (True, key_record_id_if_linked) so the
    caller can warn the user that the key record was NOT deleted.
    Returns (False, None) if the entry was not found.
    """
    log = _read_log()
    entry = log['entries'].get(entry_id)
    if entry is None:
        return False, None
    linked_kr = entry.get('key_record_id')
    del log['entries'][entry_id]
    _write_log(log)
    return True, linked_kr


def add_photo(entry_id: str, stored_relative_path: str) -> dict[str, Any] | None:
    """Append a stored relative path to entry.photos. Returns updated entry."""
    log = _read_log()
    entry = log['entries'].get(entry_id)
    if entry is None:
        return None
    photos: list[str] = entry.setdefault('photos', [])
    if stored_relative_path not in photos:
        photos.append(stored_relative_path)
    entry['updated'] = _now_str()
    _write_log(log)
    return entry


def remove_photo(entry_id: str, photo_idx: int) -> dict[str, Any] | None:
    """Remove a photo by index from entry.photos. Returns updated entry."""
    log = _read_log()
    entry = log['entries'].get(entry_id)
    if entry is None:
        return None
    photos: list[str] = entry.get('photos', [])
    if 0 <= photo_idx < len(photos):
        photos.pop(photo_idx)
    entry['updated'] = _now_str()
    _write_log(log)
    return entry
