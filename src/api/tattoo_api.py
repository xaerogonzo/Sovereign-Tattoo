"""TattooApiMixin — layout previews, exports, and (Phase B2+) image management."""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any

import sv_bridge
import sv_keyrecord
import sv_tattoo

from ._helpers import _read_settings, _safe_record, _tattoo_dirs


class TattooApiMixin:
    """Tattoo Studio tab: layout rendering + export + record persistence."""

    # ===== Layout catalog enumeration =====================================

    def tattoo_list_layouts(self) -> dict[str, Any]:
        """Return the layout catalog as a JSON-friendly structure."""
        layouts = []
        for key, entry in sv_tattoo.LAYOUT_CATALOG.items():
            layouts.append({
                'key':              key,
                'label':            entry['label'],
                'group':            entry.get('group', ''),
                'defaults':         entry['defaults'],
                'param_schema':     entry['param_schema'],
                'text_exportable':  entry.get('text_exportable', False),
            })
        return {'ok': True, 'layouts': layouts, 'glyph_advance_em': sv_tattoo.GLYPH_ADVANCE_EM}

    # ===== Preview =========================================================

    def tattoo_render_preview(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        params: {encoded_string, layout, layout_params}
        Returns {ok, glyphs: [[char, x, y, rot], ...], bbox: [x0, y0, x1, y1],
                 layout, text_exportable}.

        The JS Canvas renderer multiplies glyph coords by its own font_size_px
        to convert em -> pixels.
        """
        encoded = params.get('encoded_string', '')
        layout = params.get('layout', 'paragraph')
        layout_params = params.get('layout_params') or {}
        try:
            glyphs = sv_tattoo.render_layout(encoded, layout, layout_params)
        except ValueError as e:
            return {'ok': False, 'error': str(e)}
        except Exception as e:
            return {'ok': False, 'error': f'Layout render failed: {e}'}

        entry = sv_tattoo.LAYOUT_CATALOG.get(layout, {})
        return {
            'ok':               True,
            'glyphs':           sv_tattoo.glyphs_to_payload(glyphs),
            'bbox':             list(sv_tattoo.bbox_of(glyphs)),
            'layout':           layout,
            'text_exportable':  entry.get('text_exportable', False),
        }

    # ===== Export ==========================================================

    def tattoo_export(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        params: {encoded_string, layout, layout_params, format, out_path,
                 font_size_px? (SVG/PNG only)}
        format: 'svg' | 'txt'   (Phase B2 adds 'png')

        Returns {ok, out_path, format, byte_count}.
        """
        encoded = params.get('encoded_string', '')
        layout = params.get('layout', 'paragraph')
        layout_params = params.get('layout_params') or {}
        fmt = (params.get('format') or 'svg').lower()
        out_path = params.get('out_path', '')
        if not out_path:
            return {'ok': False, 'error': 'out_path is required'}

        try:
            glyphs = sv_tattoo.render_layout(encoded, layout, layout_params)
        except ValueError as e:
            return {'ok': False, 'error': str(e)}
        except Exception as e:
            return {'ok': False, 'error': f'Layout render failed: {e}'}

        try:
            if fmt == 'svg':
                font_size = int(params.get('font_size_px', 32))
                content = sv_tattoo.render_svg(glyphs, font_size_px=font_size)
                Path(out_path).write_text(content, encoding='utf-8')
            elif fmt == 'txt':
                content = sv_tattoo.render_text(glyphs, layout)
                Path(out_path).write_text(content, encoding='utf-8')
            elif fmt == 'png':
                font_size = int(params.get('font_size_px', 32))
                sv_tattoo.render_png(glyphs, out_path, font_size_px=font_size)
            else:
                return {'ok': False, 'error': f'Unknown format: {fmt!r}'}
        except FileNotFoundError as e:
            return {'ok': False, 'error': f'Failed to write {fmt}: {e}'}
        except ImportError as e:
            return {'ok': False, 'error': f'PNG export requires Pillow: {e}'}
        except Exception as e:
            return {'ok': False, 'error': f'Failed to write {fmt}: {e}'}

        return {
            'ok':         True,
            'out_path':   out_path,
            'format':     fmt,
            'byte_count': Path(out_path).stat().st_size,
        }

    # ===== Record persistence ==============================================

    def tattoo_save_layout_to_record(
        self,
        record_id: str,
        layout: str,
        layout_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Persist the chosen layout name + params into the key record."""
        if layout not in sv_tattoo.LAYOUT_CATALOG:
            return {'ok': False, 'error': f'Unknown layout: {layout!r}'}

        record = sv_keyrecord.get_record(record_id)
        if record is None:
            return {'ok': False, 'error': f'Record {record_id!r} not found'}

        record['tattoo_layout'] = layout
        record['tattoo_layout_params'] = layout_params or {}
        saved = sv_keyrecord.save_record(record)
        return {'ok': True, 'record': _safe_record(saved)}

    # ===== Reference image management (Phase B2) ==========================

    def tattoo_image_import(self, record_id: str, src_path: str) -> dict[str, Any]:
        """
        Copy a reference image (PNG / JPG / etc.) into the vault's tattoo
        images folder and link it to a key record.

        The original file is left untouched. The copy lives at
        ``<vault>/tattoo_images/<record_id><ext>``. The record gains:
          - ``tattoo_image_path`` — relative path under the vault folder
          - ``tattoo_image_abs`` — absolute path (convenience for the GUI)
          - ``tattoo_image_imported`` — ISO timestamp
        """
        if not src_path or not Path(src_path).is_file():
            return {'ok': False, 'error': f'Source image not found: {src_path!r}'}

        record = sv_keyrecord.get_record(record_id)
        if record is None:
            return {'ok': False, 'error': f'Record {record_id!r} not found'}

        src = Path(src_path)
        ext = src.suffix.lower() or '.png'
        if ext not in ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'):
            return {'ok': False, 'error': f'Unsupported image type: {ext}'}

        dirs = _tattoo_dirs()
        dest = dirs['images'] / f'{record_id}{ext}'

        try:
            shutil.copy2(src, dest)
        except Exception as e:
            return {'ok': False, 'error': f'Failed to copy image: {e}'}

        rel = dest.relative_to(dirs['vault_root']).as_posix()
        record['tattoo_image_path'] = rel
        record['tattoo_image_abs'] = str(dest)
        record['tattoo_image_imported'] = time.strftime('%Y-%m-%d %H:%M:%S')
        saved = sv_keyrecord.save_record(record)
        return {'ok': True, 'stored_path': str(dest),
                'relative': rel, 'record': _safe_record(saved)}

    # ===== Recognition adapters (Phase B3) ================================

    def tattoo_adapters_list(self) -> dict[str, Any]:
        """
        Enumerate recognition adapters with availability flags so the GUI
        can grey out unsupported options.
        """
        settings = _read_settings()
        tess_path = settings.get('tesseract_path', '')
        adapters = []
        for a in sv_tattoo.list_adapters(tesseract_cmd=tess_path):
            adapters.append({
                'name':           a.name,
                'label':          a.label,
                'available':      a.available_now(),
                'reason':         a.reason(),
            })
        return {'ok': True, 'adapters': adapters}

    def tattoo_image_recognize(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Run an OCR adapter on a reference image.

        params: {image_path, alphabet_id?, adapter?}
          - image_path: absolute path to an image file
          - alphabet_id: optional, used to look up alphabet_chars for the
            Tesseract whitelist (ASCII-only alphabets only)
          - adapter: 'manual' | 'tesseract' | 'custom_glyph' (default: 'tesseract')

        Returns {ok, text, confidence?, adapter_used} so the side-by-side
        editor can pre-fill the recognized string for user review.
        """
        image_path = params.get('image_path', '')
        if not image_path or not Path(image_path).is_file():
            return {'ok': False, 'error': f'Image not found: {image_path!r}'}

        adapter_name = params.get('adapter', 'tesseract')
        settings = _read_settings()
        adapter = sv_tattoo.get_adapter(adapter_name,
                                        tesseract_cmd=settings.get('tesseract_path', ''))
        if adapter is None:
            return {'ok': False, 'error': f'Unknown adapter: {adapter_name!r}'}
        if not adapter.available_now():
            return {'ok': False, 'error': adapter.reason()}

        # Optional alphabet lookup for the Tesseract whitelist
        alph_chars = ''
        alph_id = params.get('alphabet_id', '')
        if alph_id:
            try:
                import json as _json
                lib_raw = _json.loads(
                    (sv_bridge.project_root() / 'sv_lib.json').read_text(encoding='utf-8')
                )
                a_full = next(
                    (x for x in lib_raw.get('alphabets', []) if x['id'] == alph_id),
                    None,
                )
                if a_full:
                    alph_chars = a_full.get('chars', '')
            except Exception:
                pass

        result = adapter.recognize(image_path, alph_chars)
        result['adapter_used'] = adapter_name
        return result

    def tattoo_image_remove(self, record_id: str) -> dict[str, Any]:
        """Detach (and delete from disk) the reference image for a record."""
        record = sv_keyrecord.get_record(record_id)
        if record is None:
            return {'ok': False, 'error': f'Record {record_id!r} not found'}
        abs_path = record.get('tattoo_image_abs', '')
        if abs_path:
            try:
                Path(abs_path).unlink(missing_ok=True)
            except Exception:
                pass
        for key in ('tattoo_image_path', 'tattoo_image_abs', 'tattoo_image_imported'):
            record.pop(key, None)
        saved = sv_keyrecord.save_record(record)
        return {'ok': True, 'record': _safe_record(saved)}
