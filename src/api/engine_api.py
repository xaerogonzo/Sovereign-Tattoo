"""EngineApiMixin — external compression engine registry (LPAQ8, PAQ8O, ZPAQ)."""

from __future__ import annotations

from typing import Any

import sv_compress
import sv_engines


class EngineApiMixin:
    """Discover, install, remove, and benchmark external compression engines."""

    def engines_list(self) -> dict[str, Any]:
        """Return the registry of external compression engines + install status."""
        try:
            return {
                'ok': True,
                'bin_dir': str(sv_engines.bin_dir()),
                'engines': sv_engines.list_engines(),
            }
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def engine_install(self, engine_id: str, source_path: str) -> dict[str, Any]:
        """Copy a user-supplied binary into bin/ as <expected_filename>."""
        try:
            path = sv_engines.install_from_path(engine_id, source_path)
            return {'ok': True, 'installed_path': path}
        except sv_engines.EngineError as e:
            return {'ok': False, 'error': str(e)}

    def engine_remove(self, engine_id: str) -> dict[str, Any]:
        removed = sv_engines.remove_engine(engine_id)
        if not removed:
            return {'ok': False, 'error': f'Engine {engine_id!r} not installed'}
        return {'ok': True}

    def engine_test(self, engine_id: str, sample: str = '') -> dict[str, Any]:
        """Round-trip a sample through the engine and report the compressed size."""
        sample_text = sample or (
            'Sovereign Tattoo compression engine test. '
            'This is a typical English sentence that should compress reasonably well.'
        )
        data = sample_text.encode('utf-8')
        try:
            c = sv_compress.compress_bytes(data, engine_id)
            d = sv_compress.decompress_bytes(c, engine_id)
            return {
                'ok': True,
                'original_bytes': len(data),
                'compressed_bytes': len(c),
                'ratio': len(c) / len(data) if data else 0,
                'roundtrip': d == data,
            }
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def test_compress(self, sample: str) -> dict[str, Any]:
        """Try every available algorithm against *sample* and return sizes."""
        try:
            data = sample.encode('utf-8')
            results: dict[str, Any] = {'original': len(data)}
            for algo in ('zlib', 'lzma'):
                try:
                    results[algo] = len(sv_compress.compress_bytes(data, algo))
                except Exception as e:
                    results[algo] = f'error: {e}'
            for engine_id in sv_compress.EXTERNAL_ALGOS:
                if sv_engines.is_installed(engine_id):
                    try:
                        results[engine_id] = len(sv_compress.compress_bytes(data, engine_id))
                    except Exception as e:
                        results[engine_id] = f'error: {e}'
            return {'ok': True, 'sizes': results}
        except Exception as e:
            return {'ok': False, 'error': str(e)}
