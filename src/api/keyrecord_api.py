"""KeyRecordApiMixin — list / get / delete / export / find key records."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import sv_keyring
import sv_keyrecord

from ._helpers import _project_root, _safe_record, label_to_filename


class KeyRecordApiMixin:
    """Vault tab: key record CRUD + lookup by encoded string."""

    def keyrecord_list(self) -> dict[str, Any]:
        try:
            records = sv_keyrecord.list_records()
            return {'ok': True, 'records': [_safe_record(r) for r in records]}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def keyrecord_get(self, record_id: str) -> dict[str, Any]:
        r = sv_keyrecord.get_record(record_id)
        if r is None:
            return {'ok': False, 'error': f'Record {record_id!r} not found'}
        return {'ok': True, 'record': _safe_record(r)}

    def keyrecord_delete(self, record_id: str) -> dict[str, Any]:
        deleted = sv_keyrecord.delete_record(record_id)
        if not deleted:
            return {'ok': False, 'error': f'Record {record_id!r} not found'}
        # Also remove from keyring
        try:
            sv_keyring.delete_password(record_id)
        except Exception:
            pass
        return {'ok': True}

    def keyrecord_export(self, record_id: str, out_path: str = '') -> dict[str, Any]:
        record = sv_keyrecord.get_record(record_id)
        if record is None:
            return {'ok': False, 'error': f'Record {record_id!r} not found'}

        if not out_path:
            base = label_to_filename(record.get('label') or record_id)
            out_path = str(
                Path(_project_root()) / f'sv_keyrecord_{base}_{record_id}.txt'
            )

        try:
            paths = sv_keyrecord.export_record_card(record, out_path)
            return {'ok': True, **paths}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def keyrecord_find_by_string(self, encoded_string: str) -> dict[str, Any]:
        """Auto-lookup a key record by the full encoded string."""
        r = sv_keyrecord.find_by_record_id_prefix(encoded_string)
        if r is None:
            r = sv_keyrecord.find_by_encoded_string(encoded_string)
        if r is None:
            return {'ok': False, 'error': 'No matching key record found'}
        return {'ok': True, 'record': _safe_record(r)}
