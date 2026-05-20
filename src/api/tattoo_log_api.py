"""
tattoo_log_api.py — TattooLogApiMixin

Exposes CRUD for the personal tattoo dossier (sv_tattoo_log.json).
This layer is the *aesthetic wrapper*: photos, placement, artist info, status.
It never reads or writes sv_key_records.json.

Also exposes tattoo_analyze_photo() which uses Claude Vision to analyse a
stored photo and return AI suggestions based on a user-supplied prompt.
The Anthropic API key is read from Windows Credential Manager at call time —
it is never stored in settings JSON or logged.
"""

from __future__ import annotations

import base64
import shutil
from pathlib import Path
from typing import Any

import keyring
import sv_tattoo_log
from api._helpers import _tattoo_dirs

_ANTHROPIC_SERVICE = 'sovereign-tattoo-config'
_ANTHROPIC_USER    = 'anthropic_api_key'


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

    # ---------------------------------------------------- Claude Vision analysis

    def tattoo_analyze_photo(
        self,
        entry_id: str,
        photo_idx: int,
        prompt: str,
    ) -> dict[str, Any]:
        """
        Send a stored tattoo photo to Claude Vision with *prompt* and return
        the AI's suggestions.

        The Anthropic API key is read from Windows Credential Manager at call
        time — it is never stored in settings JSON or passed from JS.

        Returns {ok, response, model} on success, or {ok:False, error} on
        failure (including missing API key, missing file, or API error).
        """
        try:
            # 1. Resolve photo path
            entry = sv_tattoo_log.get_entry(entry_id)
            if entry is None:
                return {'ok': False, 'error': f'Entry {entry_id!r} not found'}
            photos = entry.get('photos', [])
            if not (0 <= photo_idx < len(photos)):
                return {'ok': False, 'error': f'Photo index {photo_idx} out of range'}
            dirs = _tattoo_dirs()
            img_path = dirs['vault_root'] / photos[photo_idx]
            if not img_path.exists():
                return {'ok': False, 'error': f'Photo file not found: {img_path}'}

            # 2. Read + base64-encode the image
            img_bytes = img_path.read_bytes()
            img_b64   = base64.standard_b64encode(img_bytes).decode('ascii')
            suffix    = img_path.suffix.lower().lstrip('.')
            media_map = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
                         'png': 'image/png',  'gif': 'image/gif',
                         'webp': 'image/webp'}
            media_type = media_map.get(suffix, 'image/jpeg')

            # 3. Get API key from Credential Manager
            api_key = keyring.get_password(_ANTHROPIC_SERVICE, _ANTHROPIC_USER)
            if not api_key:
                return {
                    'ok': False,
                    'error': 'Anthropic API key not configured. Go to Settings → AI Features to add it.',
                }

            # 4. Call Claude Vision
            try:
                import anthropic
            except ImportError:
                return {
                    'ok': False,
                    'error': 'anthropic package not installed. Run: pip install anthropic',
                }

            client = anthropic.Anthropic(api_key=api_key)
            model  = 'claude-opus-4-5'

            system_msg = (
                'You are a professional tattoo design consultant with expertise in '
                'tattoo artistry, body placement, healing, and modification. '
                'When analysing a tattoo photo, give practical, specific, and '
                'thoughtful suggestions. Be honest but constructive.'
            )

            user_prompt = (prompt or '').strip() or \
                'Analyse this tattoo and suggest how it could be modified or improved.'

            message = client.messages.create(
                model=model,
                max_tokens=1024,
                system=system_msg,
                messages=[{
                    'role': 'user',
                    'content': [
                        {
                            'type': 'image',
                            'source': {
                                'type': 'base64',
                                'media_type': media_type,
                                'data': img_b64,
                            },
                        },
                        {'type': 'text', 'text': user_prompt},
                    ],
                }],
            )

            response_text = message.content[0].text if message.content else ''
            return {'ok': True, 'response': response_text, 'model': model}

        except Exception as exc:
            return {'ok': False, 'error': str(exc)}
