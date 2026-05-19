"""AlphabetApiMixin — list / save / delete alphabets, import .svlib, generate key cards."""

from __future__ import annotations

from typing import Any

import sv_bridge


class AlphabetApiMixin:
    """Alphabet library CRUD + key card generation."""

    def list_alphabets(self) -> dict[str, Any]:
        try:
            return {'ok': True, 'alphabets': sv_bridge.list_alphabets()}
        except sv_bridge.SovereignError as e:
            return {'ok': False, 'error': str(e)}

    def save_alphabet(self, entry: dict[str, Any]) -> dict[str, Any]:
        # Validate chars before persisting
        chars = entry.get('chars', '')
        if len(chars) < 2:
            return {'ok': False, 'error': 'Alphabet must have at least 2 characters'}
        if len(set(chars)) != len(chars):
            seen: set[str] = set()
            dupes: list[str] = []
            for c in chars:
                if c in seen:
                    dupes.append(repr(c))
                seen.add(c)
            return {'ok': False, 'error': f'Duplicate characters in alphabet: {", ".join(dupes)}'}
        return sv_bridge.save_alphabet(entry)

    def delete_alphabet(self, alph_id: str) -> dict[str, Any]:
        return sv_bridge.delete_alphabet(alph_id)

    def import_svlib(self, svlib_path: str) -> dict[str, Any]:
        return sv_bridge.import_svlib(svlib_path)

    def key_card(self, alph_id: str, out_path: str) -> dict[str, Any]:
        return sv_bridge.key_card(alph_id, out_path)
