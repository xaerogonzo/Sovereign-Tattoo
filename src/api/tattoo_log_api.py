"""
tattoo_log_api.py — TattooLogApiMixin

Exposes CRUD for the personal tattoo dossier (sv_tattoo_log.json).
This layer is the *aesthetic wrapper*: photos, placement, artist info, status.
It never reads or writes sv_key_records.json.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import sv_tattoo_log
from api._helpers import _tattoo_dirs


class TattooLogApiMixin:
    """Mixin providing the tattoo-log API methods to SovereignApi."""

    # ------------------------------------------------------------------ list

    def tattoo_log_list(self) -> dict[str, Any]:
        """
        Return all tattoo entries plus the enum option lists.
        Response: {ok, entries: [...], placements: [...], statuses: [...]}.
        """
        try:
            entries = sv_tattoo_log.list_entries()
            return {
                'ok': True,
                'entries': entries,
                'placements': sv_tattoo_log.PLACEMENTS,
                'statuses': sv_tattoo_log.STATUSES,
            }
        except Exception as exc:
            return {'ok': False, 'error': str(exc)}

    # ------------------------------------------------------------------ get

    def tattoo_log_get(self, entry_id: str) -> dict[str, Any]:
        """Return a single tattoo entry by ID."""
        try:
            entry = sv_tattoo_log.get_entry(entry_id)
            if entry is None:
                return {'ok': False, 'error': f'Entry {entry_id!r} not found'}
            return {'ok': True, 'entry': entry}
        except Exception as exc:
            return {'ok': False, 'error': str(exc)}

    # ---------------------------------------------------------------- create

    def tattoo_log_create(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Create a new tattoo entry.
        Accepted fields: name, type, placement, placement_notes, date_done,
        artist_name, studio_name, style, ink_colors, status, size_cm, price,
        currency, notes, key_record_id, layout, layout_params.
        """
        try:
            entry = sv_tattoo_log.create_entry(params or {})
            return {'ok': True, 'entry': entry}
        except Exception as exc:
            return {'ok': False, 'error': str(exc)}

    # ---------------------------------------------------------------- update

    def tattoo_log_update(self, entry_id: str,
                          params: dict[str, Any]) -> dict[str, Any]:
        """Update fields on an existing tattoo entry."""
        try:
            entry = sv_tattoo_log.update_entry(entry_id, params or {})
            if entry is None:
                return {'ok': False, 'error': f'Entry {entry_id!r} not found'}
            return {'ok': True, 'entry': entry}
        except Exception as exc:
            return {'ok': False, 'error': str(exc)}

    # ---------------------------------------------------------------- delete

    def tattoo_log_delete(self, entry_id: str) -> dict[str, Any]:
        """
        Delete a tattoo entry and its sidecar photos.

        SAFE DELETE CONTRACT:
        - Only the tattoo log entry + sidecar photos are removed.
        - sv_key_records.json is NEVER touched.
        - If the entry was linked to a key record, the response includes
          key_record_unlinked=True + key_record_id so the GUI can warn the user
          that their encoded data is still safe.
        """
        try:
            entry = sv_tattoo_log.get_entry(entry_id)
            if entry is None:
                return {'ok': False, 'error': f'Entry {entry_id!r} not found'}

            # Remove sidecar photos from disk
            dirs = _tattoo_dirs()
            for rel_path in entry.get('photos', []):
                abs_path = dirs['vault_root'] / rel_path
                if abs_path.exists():
                    try:
                        abs_path.unlink()
                    except OSError:
                        pass  # best-effort; don't abort the delete

            ok, linked_kr = sv_tattoo_log.delete_entry(entry_id)
            if not ok:
                return {'ok': False, 'error': f'Entry {entry_id!r} not found'}

            result: dict[str, Any] = {'ok': True}
            if linked_kr:
                result['key_record_unlinked'] = True
                result['key_record_id'] = linked_kr
            return result
        except Exception as exc:
            return {'ok': False, 'error': str(exc)}

    # ------------------------------------------------------------- add photo

    def tattoo_log_add_photo(self, entry_id: str, src_path: str) -> dict[str, Any]:
        """
        Copy *src_path* (any image file) into <vault>/tattoo_images/
        named <entry_id>_N.<ext>, and record the relative path in the entry.
        Returns {ok, entry, stored_path}.
        """
        try:
            entry = sv_tattoo_log.get_entry(entry_id)
            if entry is None:
                return {'ok': False, 'error': f'Entry {entry_id!r} not found'}

            src = Path(src_path)
            if not src.exists():
                return {'ok': False, 'error': f'Source file not found: {src_path!r}'}

            dirs = _tattoo_dirs()
            # Pick the next available index for this entry
            n = len(entry.get('photos', []))
            dest_name = f'{entry_id}_{n}{src.suffix.lower()}'
            dest = dirs['images'] / dest_name
            # Avoid clobber if a file with that name already exists
            while dest.exists():
                n += 1
                dest_name = f'{entry_id}_{n}{src.suffix.lower()}'
                dest = dirs['images'] / dest_name

            shutil.copy2(str(src), str(dest))

            # Store as a relative path from vault_root
            rel = str(dest.relative_to(dirs['vault_root']))
            updated = sv_tattoo_log.add_photo(entry_id, rel)
            return {'ok': True, 'entry': updated, 'stored_path': str(dest)}
        except Exception as exc:
            return {'ok': False, 'error': str(exc)}

    # ---------------------------------------------------------- remove photo

    def tattoo_log_remove_photo(self, entry_id: str,
                                photo_idx: int) -> dict[str, Any]:
        """Remove a photo by index (0-based). Deletes the file from disk."""
        try:
            entry = sv_tattoo_log.get_entry(entry_id)
            if entry is None:
                return {'ok': False, 'error': f'Entry {entry_id!r} not found'}

            photos = entry.get('photos', [])
            if not (0 <= photo_idx < len(photos)):
                return {'ok': False, 'error': f'Photo index {photo_idx} out of range'}

            rel_path = photos[photo_idx]
            dirs = _tattoo_dirs()
            abs_path = dirs['vault_root'] / rel_path
            if abs_path.exists():
                abs_path.unlink()

            updated = sv_tattoo_log.remove_photo(entry_id, photo_idx)
            return {'ok': True, 'entry': updated}
        except Exception as exc:
            return {'ok': False, 'error': str(exc)}

    # ----------------------------------------------------------- link record

    def tattoo_log_link_record(self, entry_id: str,
                               key_record_id: str) -> dict[str, Any]:
        """Link a tattoo entry to a key record; changes type to 'encoded'."""
        try:
            entry = sv_tattoo_log.update_entry(entry_id, {
                'key_record_id': key_record_id,
                'type': 'encoded',
            })
            if entry is None:
                return {'ok': False, 'error': f'Entry {entry_id!r} not found'}
            return {'ok': True, 'entry': entry}
        except Exception as exc:
            return {'ok': False, 'error': str(exc)}

    # --------------------------------------------------------- unlink record

    def tattoo_log_unlink_record(self, entry_id: str) -> dict[str, Any]:
        """
        Remove the key-record link from a tattoo entry; changes type to 'art'.
        The key record in sv_key_records.json is NOT touched.
        """
        try:
            entry = sv_tattoo_log.update_entry(entry_id, {
                'key_record_id': None,
                'type': 'art',
            })
            if entry is None:
                return {'ok': False, 'error': f'Entry {entry_id!r} not found'}
            return {'ok': True, 'entry': entry}
        except Exception as exc:
            return {'ok': False, 'error': str(exc)}
