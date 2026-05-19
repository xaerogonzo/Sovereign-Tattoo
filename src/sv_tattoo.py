"""
sv_tattoo.py — Layout engine for the Sovereign Tattoo Studio.

Pure-Python module. No GUI / no I/O dependencies. Three responsibilities:

1. **Layouts** — Pure functions that take an encoded string and parameters,
   return a list of positioned glyphs (`LayoutGlyph`) in em-relative coords.
2. **Renderers** — Convert glyph lists to SVG strings, plain text, or
   payloads for the JS Canvas (the API layer passes the dataclass to JS
   as a plain dict).
3. **Recognition adapters** (Phase B3, stubbed here) — Plug-in image-to-text
   strategies (Manual / Tesseract / future Custom).

The key abstraction is `LayoutGlyph(char, x, y, rotation_deg)`. Every renderer
consumes the same glyph list, so adding a layout only requires writing one
function — Canvas/SVG/PNG/text all reuse the same data.

Coordinates are in **em units** (font-size-relative). The renderer scales to
pixels by multiplying by the requested font size.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Callable, NamedTuple


# ---------------------------------------------------------------------------
# Core data type
# ---------------------------------------------------------------------------

class LayoutGlyph(NamedTuple):
    """One positioned character.

    Coordinates are em-units relative to the layout's natural origin. The
    renderer translates to pixels via its own scale factor.
    """
    char: str          # one Python codepoint (works for BMP including ♠♣♥♦)
    x: float           # em offset from origin (right-positive)
    y: float           # em offset from origin (down-positive — matches Canvas/SVG)
    rotation_deg: float  # rotation around (x, y), 0 = upright


# Default glyph advance width in em for the bundled DejaVu Sans Mono.
# DejaVu Sans Mono glyphs are 600 units in a 1024-unit em square → 0.586 em.
# We round up slightly to leave breathing room between adjacent chars on curves.
GLYPH_ADVANCE_EM = 0.62


# ---------------------------------------------------------------------------
# Arc-length helper — the math heart of every curved layout
# ---------------------------------------------------------------------------

def _advance_along_path(
    path_fn: Callable[[float], tuple[float, float]],
    current_t: float,
    arc_target: float,
    sub_steps: int = 200,
) -> float:
    """
    Walk along *path_fn* starting at *current_t* until the cumulative arc
    length from the start point reaches *arc_target*. Returns the new t.

    The trick is to scale each sub-step by the *local speed* |path'(t)|, so
    we always advance by ~equal arc-length increments regardless of how the
    parameter t maps to position. This is what prevents bunching on inner
    spiral radii and stretching at outer ones.

    Algorithm: estimate the speed at the current point via finite differences,
    pick the parameter step `dt = (target_step / speed)`, integrate forward.
    When the next sub-segment would overshoot *arc_target*, linearly
    interpolate inside that segment to land exactly on target.

    *sub_steps* — how finely we sub-divide *arc_target*. 200 gives <0.5%
    arc-length error for circles, spirals, and sinusoids up to amplitude ≈ 5.
    """
    eps = 1e-6        # finite-difference tangent estimate
    safety = 1e-9     # degenerate-point speed threshold

    t = current_t
    arc = 0.0
    target_step = arc_target / sub_steps if sub_steps > 0 else arc_target

    # Cap iterations to defend against pathological paths (cusps, loops).
    for _ in range(sub_steps * 10):
        if arc >= arc_target:
            return t

        # Local speed estimate via centred finite difference
        x_a, y_a = path_fn(t)
        x_b, y_b = path_fn(t + eps)
        speed = math.hypot(x_b - x_a, y_b - y_a) / eps
        if speed < safety:
            # Cusp / degenerate point — nudge through it
            t += eps
            continue

        dt = target_step / speed
        x_c, y_c = path_fn(t + dt)
        seg = math.hypot(x_c - x_a, y_c - y_a)

        if arc + seg >= arc_target:
            # Linear interp inside this sub-segment to land exactly on target
            frac = (arc_target - arc) / seg if seg > 0 else 0.0
            return t + dt * frac

        arc += seg
        t += dt

    return t  # ran out of iterations — return our best estimate


def _tangent_angle_deg(
    path_fn: Callable[[float], tuple[float, float]],
    t: float,
    eps: float = 1e-5,
) -> float:
    """
    Return the tangent direction at *t* in degrees (0 = pointing right,
    90 = pointing down — matching the Canvas/SVG y-down convention).
    """
    x0, y0 = path_fn(t)
    x1, y1 = path_fn(t + eps)
    return math.degrees(math.atan2(y1 - y0, x1 - x0))


# ---------------------------------------------------------------------------
# MVP layouts
# ---------------------------------------------------------------------------

def _layout_paragraph(chars: list[str], params: dict) -> list[LayoutGlyph]:
    """
    Classic word-wrap rectangle. Wraps at *width_chars* columns; no rotation.
    Params: {width_chars: int, line_height_em: float}.
    """
    width = int(params.get('width_chars', 24))
    line_h = float(params.get('line_height_em', 1.4))
    glyphs: list[LayoutGlyph] = []
    for i, c in enumerate(chars):
        col = i % width
        row = i // width
        glyphs.append(LayoutGlyph(c, col * GLYPH_ADVANCE_EM, row * line_h, 0.0))
    return glyphs


def _layout_column_multi(chars: list[str], params: dict) -> list[LayoutGlyph]:
    """
    Matrix-code aesthetic: N vertical columns read top-to-bottom (or
    bottom-to-top), left column first. Chars wrap to the next column when
    the current one fills.

    Params: {columns: int, col_spacing_em: float, direction: 'down'|'up',
             max_rows: int (optional cap; default: ceil(len/columns))}.
    """
    columns = max(1, int(params.get('columns', 4)))
    col_spacing = float(params.get('col_spacing_em', 1.2))
    direction = params.get('direction', 'down')
    n = len(chars)
    rows = int(params.get('max_rows') or math.ceil(n / columns))

    glyphs: list[LayoutGlyph] = []
    for i, c in enumerate(chars):
        col = i // rows
        row_in_col = i % rows
        if direction == 'up':
            row_in_col = (rows - 1) - row_in_col
        glyphs.append(LayoutGlyph(c, col * col_spacing, row_in_col * 1.4, 0.0))
    return glyphs


def _layout_circle(chars: list[str], params: dict) -> list[LayoutGlyph]:
    """
    Single ring. Characters distributed by arc-length, optionally rotated to
    follow the tangent so they 'lean into' the curve.

    Params: {radius_em: float, start_angle_deg: float, rotate_chars: bool,
             clockwise: bool}.
    """
    r = float(params.get('radius_em', 8))
    start_deg = float(params.get('start_angle_deg', -90))  # top of the circle
    rotate = bool(params.get('rotate_chars', True))
    clockwise = bool(params.get('clockwise', True))
    direction = 1 if clockwise else -1

    def path(theta: float) -> tuple[float, float]:
        return r * math.cos(theta), r * math.sin(theta) * direction

    glyphs: list[LayoutGlyph] = []
    t = math.radians(start_deg)
    for i, c in enumerate(chars):
        x, y = path(t)
        if rotate:
            rot = _tangent_angle_deg(path, t)
        else:
            rot = 0.0
        glyphs.append(LayoutGlyph(c, x, y, rot))
        # Advance one glyph-width along the arc
        t = _advance_along_path(path, t, GLYPH_ADVANCE_EM)
    return glyphs


def _layout_spiral_inward(chars: list[str], params: dict) -> list[LayoutGlyph]:
    """
    Archimedean spiral from *start_radius_em* down to *end_radius_em*.
    Characters spaced by arc length so they neither bunch nor stretch.

    Params: {start_radius_em: float, end_radius_em: float, rotate_chars: bool,
             start_angle_deg: float}.

    The spiral parameter `k` (radius decrement per radian) is set so the
    given char count fits between start and end radii. If the encoded string
    is too long for that radius range, characters beyond the inner radius
    will overshoot into negative-radius territory; the GUI should warn.
    """
    r0 = float(params.get('start_radius_em', 10))
    r1 = float(params.get('end_radius_em', 2))
    rotate = bool(params.get('rotate_chars', True))
    start_deg = float(params.get('start_angle_deg', 0))

    # Total angular sweep estimate: pick something proportional to the
    # number of chars but bounded so we don't over-revolve when char count
    # is tiny.
    n = max(1, len(chars))
    # Heuristic: average radius * sweep ≈ total arc length needed
    avg_r = (r0 + r1) / 2 if r0 > 0 and r1 > 0 else max(r0, r1, 1)
    total_arc = n * GLYPH_ADVANCE_EM
    total_sweep = total_arc / max(avg_r, 0.5)  # radians
    if total_sweep < 0.1:
        total_sweep = 0.1
    k = (r1 - r0) / total_sweep  # negative: shrinking inward

    def path(theta: float) -> tuple[float, float]:
        r = r0 + k * theta
        return r * math.cos(theta), r * math.sin(theta)

    glyphs: list[LayoutGlyph] = []
    t = math.radians(start_deg)
    for i, c in enumerate(chars):
        x, y = path(t)
        rot = _tangent_angle_deg(path, t) if rotate else 0.0
        glyphs.append(LayoutGlyph(c, x, y, rot))
        t = _advance_along_path(path, t, GLYPH_ADVANCE_EM)
    return glyphs


def _layout_wave(chars: list[str], params: dict) -> list[LayoutGlyph]:
    """
    Sinusoidal path y = A·sin(f·x), arc-length-stepped so characters are
    evenly spaced along the curve (not along the x axis).

    Params: {amplitude_em: float, frequency: float, rotate_chars: bool}.
    Length is implied by the character count.
    """
    amp = float(params.get('amplitude_em', 2))
    freq = float(params.get('frequency', 2)) * math.pi / 10  # period ≈ 10 em / freq
    rotate = bool(params.get('rotate_chars', True))

    def path(x: float) -> tuple[float, float]:
        return x, amp * math.sin(freq * x)

    glyphs: list[LayoutGlyph] = []
    t = 0.0
    for i, c in enumerate(chars):
        x, y = path(t)
        rot = _tangent_angle_deg(path, t) if rotate else 0.0
        glyphs.append(LayoutGlyph(c, x, y, rot))
        t = _advance_along_path(path, t, GLYPH_ADVANCE_EM)
    return glyphs


# ---------------------------------------------------------------------------
# Shared geometry helpers for the extended layout library
# ---------------------------------------------------------------------------

def _circular_lerp_angle(a0: float, a1: float, t: float) -> float:
    """
    Blend two angles (in degrees) by fraction *t* ∈ [0, 1] using circular mean.
    Avoids the 359°→1° wrap-around discontinuity.
    """
    r0, r1 = math.radians(a0), math.radians(a1)
    x = math.cos(r0) * (1 - t) + math.cos(r1) * t
    y = math.sin(r0) * (1 - t) + math.sin(r1) * t
    return math.degrees(math.atan2(y, x))


def _regular_polygon_vertices(n: int, radius: float, start_deg: float = -90.0
                               ) -> list[tuple[float, float]]:
    """Return *n* vertices of a regular polygon inscribed in *radius*."""
    return [
        (radius * math.cos(math.radians(start_deg + i * 360 / n)),
         radius * math.sin(math.radians(start_deg + i * 360 / n)))
        for i in range(n)
    ]


def _star_vertices(n_points: int, outer_r: float, inner_r: float,
                   start_deg: float = -90.0) -> list[tuple[float, float]]:
    """Return 2*n_points vertices alternating between outer and inner radius."""
    verts = []
    for i in range(2 * n_points):
        angle_deg = start_deg + i * 180 / n_points
        r = outer_r if i % 2 == 0 else inner_r
        verts.append((r * math.cos(math.radians(angle_deg)),
                      r * math.sin(math.radians(angle_deg))))
    return verts


def _walk_polygon_path(
    vertices: list[tuple[float, float]],
    chars: list[str],
    *,
    rotate: bool = True,
    closed: bool = True,
    smooth_em: float = GLYPH_ADVANCE_EM * 1.0,
) -> list[LayoutGlyph]:
    """
    Walk *chars* along the edges of a polygon, arc-length-stepped.

    Position: linear interpolation along whichever edge contains the current
    arc-length parameter *s*.

    Rotation: within *smooth_em* of a vertex the tangent is blended between
    the incoming and outgoing edge directions via circular lerp — so characters
    arc through sharp corners instead of snapping.

    *smooth_em* = 0 disables blending (instant snap).
    """
    if not vertices or not chars:
        return []

    # Build edges list (close polygon if requested)
    edges = list(zip(vertices, vertices[1:]))
    if closed:
        edges.append((vertices[-1], vertices[0]))

    # Precompute per-edge: length, cumulative arc start, unit tangent angle (deg)
    edge_len: list[float] = []
    edge_start: list[float] = []  # cumulative arc length at start of each edge
    edge_angle: list[float] = []  # tangent direction of each edge
    arc_acc = 0.0
    for (ax, ay), (bx, by) in edges:
        length = math.hypot(bx - ax, by - ay)
        edge_len.append(max(length, 1e-9))
        edge_start.append(arc_acc)
        arc_acc += length
        edge_angle.append(math.degrees(math.atan2(by - ay, bx - ax)))
    total_perimeter = arc_acc

    # Precompute cumulative arc length at each *vertex* (same as edge_start)
    vertex_s: list[float] = list(edge_start)  # vertex i starts edge i

    def _position_at(s: float) -> tuple[float, float]:
        """Linear-interpolate position at arc length *s* (with wrap-around)."""
        s = s % total_perimeter
        for i, (est, elen) in enumerate(zip(edge_start, edge_len)):
            end = est + elen
            if s <= end + 1e-9:
                frac = (s - est) / elen
                (ax, ay), (bx, by) = edges[i]
                return ax + frac * (bx - ax), ay + frac * (by - ay)
        (ax, ay), (bx, by) = edges[-1]
        return bx, by

    def _angle_at(s: float) -> float:
        """Blended tangent angle at arc length *s*."""
        if not rotate:
            return 0.0
        s_mod = s % total_perimeter
        # Find which edge we're on
        edge_idx = 0
        for i, (est, elen) in enumerate(zip(edge_start, edge_len)):
            if s_mod <= est + elen + 1e-9:
                edge_idx = i
                break

        base_angle = edge_angle[edge_idx]
        if smooth_em <= 0:
            return base_angle

        n_edges = len(edges)
        # Check proximity to start-vertex of this edge (= end-vertex of previous edge)
        dist_to_start = s_mod - edge_start[edge_idx]
        if dist_to_start < smooth_em:
            prev_idx = (edge_idx - 1) % n_edges
            prev_angle = edge_angle[prev_idx]
            # t=0: midpoint of incoming edge, t=1: start of outgoing edge
            t = dist_to_start / smooth_em
            return _circular_lerp_angle(prev_angle, base_angle, 0.5 + 0.5 * t)

        # Check proximity to end-vertex of this edge
        dist_to_end = edge_start[edge_idx] + edge_len[edge_idx] - s_mod
        if dist_to_end < smooth_em:
            next_idx = (edge_idx + 1) % n_edges
            next_angle = edge_angle[next_idx]
            t = (smooth_em - dist_to_end) / smooth_em  # 0 at start of window, 1 at vertex
            return _circular_lerp_angle(base_angle, next_angle, 0.5 * t)

        return base_angle

    glyphs: list[LayoutGlyph] = []
    s = 0.0
    for c in chars:
        x, y = _position_at(s)
        rot = _angle_at(s)
        glyphs.append(LayoutGlyph(c, x, y, rot))
        s += GLYPH_ADVANCE_EM
    return glyphs


# ---------------------------------------------------------------------------
# Extended layout library — LINEAR group
# ---------------------------------------------------------------------------

def _layout_column_single(chars: list[str], params: dict) -> list[LayoutGlyph]:
    """Single vertical column. Alias of column_multi with columns=1."""
    p = dict(params)
    p['columns'] = 1
    return _layout_column_multi(chars, p)


def _layout_boustrophedon(chars: list[str], params: dict) -> list[LayoutGlyph]:
    """
    Snake / ox-plow: even rows go left-to-right, odd rows right-to-left.
    Characters remain upright. Params: {width_chars, line_height_em}.
    """
    width = max(1, int(params.get('width_chars', 20)))
    line_h = float(params.get('line_height_em', 1.4))
    glyphs: list[LayoutGlyph] = []
    for i, c in enumerate(chars):
        row = i // width
        col = i % width
        if row % 2 == 1:
            col = (width - 1) - col   # reverse direction
        glyphs.append(LayoutGlyph(c, col * GLYPH_ADVANCE_EM, row * line_h, 0.0))
    return glyphs


def _layout_border_rect(chars: list[str], params: dict) -> list[LayoutGlyph]:
    """
    Characters walk the perimeter of a rectangle clockwise (top → right → bottom
    reversed → left reversed). Params: {width_chars, height_chars, rotate_chars}.
    """
    w = max(2, int(params.get('width_chars', 20)))
    h = max(2, int(params.get('height_chars', 12)))
    rotate = bool(params.get('rotate_chars', True))
    sx = GLYPH_ADVANCE_EM
    sy = 1.4
    verts = [
        (0.0,        0.0),
        (w * sx,     0.0),
        (w * sx,     h * sy),
        (0.0,        h * sy),
    ]
    return _walk_polygon_path(verts, chars, rotate=rotate, closed=True)


def _layout_stagger(chars: list[str], params: dict) -> list[LayoutGlyph]:
    """
    Staggered / brick-pattern rows: odd rows are offset by half a glyph width.
    Params: {width_chars, line_height_em}.
    """
    width = max(1, int(params.get('width_chars', 20)))
    line_h = float(params.get('line_height_em', 1.4))
    glyphs: list[LayoutGlyph] = []
    for i, c in enumerate(chars):
        row = i // width
        col = i % width
        offset = GLYPH_ADVANCE_EM * 0.5 if row % 2 == 1 else 0.0
        glyphs.append(LayoutGlyph(c, col * GLYPH_ADVANCE_EM + offset, row * line_h, 0.0))
    return glyphs


def _layout_grid_fill(chars: list[str], params: dict) -> list[LayoutGlyph]:
    """
    Tight grid fill: like paragraph but with compact 1.0× spacing.
    Params: {width_chars, row_spacing_em}.
    """
    width = max(1, int(params.get('width_chars', 24)))
    row_h = float(params.get('row_spacing_em', 1.0))
    glyphs: list[LayoutGlyph] = []
    for i, c in enumerate(chars):
        col = i % width
        row = i // width
        glyphs.append(LayoutGlyph(c, col * GLYPH_ADVANCE_EM, row * row_h, 0.0))
    return glyphs


def _layout_pyramid_up(chars: list[str], params: dict) -> list[LayoutGlyph]:
    """
    Upward-widening pyramid: row r has r+1 characters, centered horizontally.
    Params: {line_height_em}.
    """
    line_h = float(params.get('line_height_em', 1.4))
    glyphs: list[LayoutGlyph] = []
    row = 0
    i = 0
    while i < len(chars):
        row_width = row + 1
        row_chars = chars[i:i + row_width]
        center_x = -(len(row_chars) - 1) * GLYPH_ADVANCE_EM / 2
        for j, c in enumerate(row_chars):
            glyphs.append(LayoutGlyph(c, center_x + j * GLYPH_ADVANCE_EM,
                                       row * line_h, 0.0))
        i += row_width
        row += 1
    return glyphs


def _layout_pyramid_down(chars: list[str], params: dict) -> list[LayoutGlyph]:
    """
    Downward-narrowing inverted pyramid: first row is widest.
    Params: {max_width_chars, line_height_em}.
    """
    n = len(chars)
    line_h = float(params.get('line_height_em', 1.4))
    # Compute max_width so the total chars fit in a triangular arrangement
    max_w = int(params.get('max_width_chars', 0))
    if max_w < 1:
        # Estimate: n = max_w + (max_w-1) + ... ≈ max_w*(max_w+1)/2
        max_w = max(1, int((-1 + math.sqrt(1 + 8 * n)) / 2))
    glyphs: list[LayoutGlyph] = []
    i = 0
    row = 0
    w = max_w
    while i < len(chars) and w >= 1:
        row_chars = chars[i:i + w]
        center_x = -(len(row_chars) - 1) * GLYPH_ADVANCE_EM / 2
        for j, c in enumerate(row_chars):
            glyphs.append(LayoutGlyph(c, center_x + j * GLYPH_ADVANCE_EM,
                                       row * line_h, 0.0))
        i += w
        row += 1
        w -= 1
    return glyphs


def _layout_hourglass(chars: list[str], params: dict) -> list[LayoutGlyph]:
    """
    Hourglass: wide top (pyramid_down) then wide bottom (pyramid_up), meeting
    at a narrow middle. Params: {line_height_em}.
    """
    line_h = float(params.get('line_height_em', 1.4))
    half = len(chars) // 2
    top_chars = chars[:half]
    bot_chars = chars[half:]
    top = _layout_pyramid_down(top_chars, params)
    bot = _layout_pyramid_up(bot_chars, params)
    # Shift bottom half below top half
    top_max_y = max((g.y for g in top), default=0.0)
    bot_shifted = [LayoutGlyph(g.char, g.x, g.y + top_max_y + line_h,
                               g.rotation_deg) for g in bot]
    return top + bot_shifted


def _layout_diamond_fill(chars: list[str], params: dict) -> list[LayoutGlyph]:
    """
    Filled diamond: rows widen to the middle then narrow, all centered.
    Params: {line_height_em, max_width_chars}.
    """
    line_h = float(params.get('line_height_em', 1.4))
    n = len(chars)
    # Calculate half-height so total chars ≈ n
    # half_h rows: widths 1, 3, 5, ... (odd rows), sum = half_h^2
    half_h = max(1, int(math.sqrt(n / 2)))
    widths: list[int] = []
    for r in range(half_h):
        widths.append(2 * r + 1)
    for r in range(half_h - 1, 0, -1):
        widths.append(2 * r - 1)
    glyphs: list[LayoutGlyph] = []
    i = 0
    for row_idx, w in enumerate(widths):
        row_chars = chars[i:i + w]
        if not row_chars:
            break
        center_x = -(len(row_chars) - 1) * GLYPH_ADVANCE_EM / 2
        for j, c in enumerate(row_chars):
            glyphs.append(LayoutGlyph(c, center_x + j * GLYPH_ADVANCE_EM,
                                       row_idx * line_h, 0.0))
        i += w
    return glyphs


# ---------------------------------------------------------------------------
# Extended layout library — RADIAL group
# ---------------------------------------------------------------------------

def _layout_arc(chars: list[str], params: dict) -> list[LayoutGlyph]:
    """
    Partial-circle arc. Params: {radius_em, start_angle_deg, span_deg,
    rotate_chars, clockwise}.
    span_deg < 360 makes it an arc rather than a full ring.
    """
    r = float(params.get('radius_em', 8))
    start_deg = float(params.get('start_angle_deg', -120))
    span_deg = float(params.get('span_deg', 240))
    rotate = bool(params.get('rotate_chars', True))
    clockwise = bool(params.get('clockwise', True))
    direction = 1 if clockwise else -1
    # Max arc length available
    max_arc = abs(math.radians(span_deg)) * r

    def path(theta: float) -> tuple[float, float]:
        return r * math.cos(theta), r * math.sin(theta) * direction

    glyphs: list[LayoutGlyph] = []
    t = math.radians(start_deg)
    arc_used = 0.0
    for c in chars:
        if arc_used >= max_arc:
            break
        x, y = path(t)
        rot = _tangent_angle_deg(path, t) if rotate else 0.0
        glyphs.append(LayoutGlyph(c, x, y, rot))
        t = _advance_along_path(path, t, GLYPH_ADVANCE_EM)
        arc_used += GLYPH_ADVANCE_EM
    return glyphs


def _layout_spiral_outward(chars: list[str], params: dict) -> list[LayoutGlyph]:
    """
    Archimedean spiral from inner radius outward.
    Params: {start_radius_em, end_radius_em, start_angle_deg, rotate_chars}.
    """
    p = dict(params)
    # Swap defaults so it looks outward by default
    if 'start_radius_em' not in p:
        p['start_radius_em'] = 2.0
    if 'end_radius_em' not in p:
        p['end_radius_em'] = 10.0
    return _layout_spiral_inward(chars, p)


def _layout_concentric(chars: list[str], params: dict) -> list[LayoutGlyph]:
    """
    Concentric rings: fill inner ring first, then next larger ring, etc.
    Params: {inner_radius_em, ring_spacing_em, start_angle_deg, rotate_chars}.
    """
    r_inner = float(params.get('inner_radius_em', 3))
    spacing = float(params.get('ring_spacing_em', 1.5))
    start_deg = float(params.get('start_angle_deg', -90))
    rotate = bool(params.get('rotate_chars', True))

    glyphs: list[LayoutGlyph] = []
    i = 0
    ring = 0
    while i < len(chars):
        r = r_inner + ring * spacing
        capacity = max(1, int(math.floor(2 * math.pi * r / GLYPH_ADVANCE_EM)))
        ring_chars = chars[i:i + capacity]

        def path(theta: float, _r: float = r) -> tuple[float, float]:
            return _r * math.cos(theta), _r * math.sin(theta)

        t = math.radians(start_deg)
        for c in ring_chars:
            x, y = path(t)
            rot = _tangent_angle_deg(path, t) if rotate else 0.0
            glyphs.append(LayoutGlyph(c, x, y, rot))
            t = _advance_along_path(path, t, GLYPH_ADVANCE_EM)

        i += len(ring_chars)
        ring += 1
    return glyphs


def _layout_double_ring(chars: list[str], params: dict) -> list[LayoutGlyph]:
    """
    Two concentric rings: inner ring filled first, then outer.
    Chars read continuously across both rings.
    Params: {inner_radius_em, outer_radius_em, start_angle_deg, rotate_chars}.
    """
    r_in = float(params.get('inner_radius_em', 5))
    r_out = float(params.get('outer_radius_em', 8))
    start_deg = float(params.get('start_angle_deg', -90))
    rotate = bool(params.get('rotate_chars', True))

    def make_ring_glyphs(ring_chars: list[str], r: float) -> list[LayoutGlyph]:
        def path(theta: float, _r: float = r) -> tuple[float, float]:
            return _r * math.cos(theta), _r * math.sin(theta)
        out: list[LayoutGlyph] = []
        t = math.radians(start_deg)
        for c in ring_chars:
            x, y = path(t)
            rot = _tangent_angle_deg(path, t) if rotate else 0.0
            out.append(LayoutGlyph(c, x, y, rot))
            t = _advance_along_path(path, t, GLYPH_ADVANCE_EM)
        return out

    inner_cap = max(1, int(math.floor(2 * math.pi * r_in / GLYPH_ADVANCE_EM)))
    inner_chars = chars[:inner_cap]
    outer_chars = chars[inner_cap:]
    return make_ring_glyphs(inner_chars, r_in) + make_ring_glyphs(outer_chars, r_out)


def _layout_radial_spokes(chars: list[str], params: dict) -> list[LayoutGlyph]:
    """
    N spokes radiating from center outward; chars distributed evenly among spokes.
    Params: {spokes, radius_em, rotate_chars}.
    """
    n_spokes = max(2, int(params.get('spokes', 8)))
    radius = float(params.get('radius_em', 8))
    rotate = bool(params.get('rotate_chars', True))

    glyphs: list[LayoutGlyph] = []
    for i, c in enumerate(chars):
        spoke = i % n_spokes
        pos_on_spoke = i // n_spokes
        angle_deg = spoke * 360 / n_spokes - 90
        angle_rad = math.radians(angle_deg)
        dist = (pos_on_spoke + 0.5) * GLYPH_ADVANCE_EM
        if dist > radius:
            break
        x = dist * math.cos(angle_rad)
        y = dist * math.sin(angle_rad)
        rot = angle_deg if rotate else 0.0
        glyphs.append(LayoutGlyph(c, x, y, rot))
    return glyphs


def _layout_sunburst(chars: list[str], params: dict) -> list[LayoutGlyph]:
    """
    Sunburst: alternating long and short spokes. Characters fill long spokes,
    then short spokes. Params: {spokes, outer_radius_em, inner_radius_em, rotate_chars}.
    """
    n = max(2, int(params.get('spokes', 8)))  # number of LONG spokes (= short spokes)
    r_long = float(params.get('outer_radius_em', 9))
    r_short = float(params.get('inner_radius_em', 5))
    rotate = bool(params.get('rotate_chars', True))

    glyphs: list[LayoutGlyph] = []
    # Interleave: long spoke 0, short spoke 0, long spoke 1, short spoke 1, ...
    for i, c in enumerate(chars):
        total_spokes = 2 * n
        spoke_idx = i % total_spokes
        pos_along = i // total_spokes
        is_long = (spoke_idx % 2 == 0)
        r_max = r_long if is_long else r_short
        angle_deg = spoke_idx * 360 / total_spokes - 90
        angle_rad = math.radians(angle_deg)
        dist = (pos_along + 0.5) * GLYPH_ADVANCE_EM
        if dist > r_max:
            break
        x = dist * math.cos(angle_rad)
        y = dist * math.sin(angle_rad)
        rot = angle_deg if rotate else 0.0
        glyphs.append(LayoutGlyph(c, x, y, rot))
    return glyphs


# ---------------------------------------------------------------------------
# Extended layout library — PATH group
# ---------------------------------------------------------------------------

def _layout_zigzag(chars: list[str], params: dict) -> list[LayoutGlyph]:
    """
    Triangular wave (zigzag): two alternating diagonal segments.
    Arc-length-stepped so chars are evenly spaced.
    Params: {amplitude_em, wavelength_em, rotate_chars}.
    """
    amp = float(params.get('amplitude_em', 2.5))
    wl = float(params.get('wavelength_em', 4.0))  # full V-cycle horizontal width
    rotate = bool(params.get('rotate_chars', True))

    half_wl = wl / 2

    def path(x: float) -> tuple[float, float]:
        # Piecewise-linear: x mod wavelength → triangle wave y
        cycle_x = x % wl
        if cycle_x < half_wl:
            y = amp * (cycle_x / half_wl)
        else:
            y = amp * (2.0 - cycle_x / half_wl)
        return x, y - amp / 2  # vertically centered

    glyphs: list[LayoutGlyph] = []
    t = 0.0
    for c in chars:
        x, y = path(t)
        rot = _tangent_angle_deg(path, t) if rotate else 0.0
        glyphs.append(LayoutGlyph(c, x, y, rot))
        t = _advance_along_path(path, t, GLYPH_ADVANCE_EM)
    return glyphs


def _layout_double_wave(chars: list[str], params: dict) -> list[LayoutGlyph]:
    """
    Two parallel sinusoids phase-shifted by π; chars alternate between strands.
    Params: {amplitude_em, frequency, strand_gap_em, rotate_chars}.
    """
    amp = float(params.get('amplitude_em', 1.5))
    freq = float(params.get('frequency', 2)) * math.pi / 10
    gap = float(params.get('strand_gap_em', 1.2))
    rotate = bool(params.get('rotate_chars', True))

    def path0(x: float) -> tuple[float, float]:
        return x,  gap / 2 + amp * math.sin(freq * x)

    def path1(x: float) -> tuple[float, float]:
        return x, -gap / 2 + amp * math.sin(freq * x + math.pi)

    # Walk both strands in parallel: even chars → strand 0, odd → strand 1
    t0, t1 = 0.0, 0.0
    glyphs: list[LayoutGlyph] = []
    for i, c in enumerate(chars):
        if i % 2 == 0:
            x, y = path0(t0)
            rot = _tangent_angle_deg(path0, t0) if rotate else 0.0
            glyphs.append(LayoutGlyph(c, x, y, rot))
            t0 = _advance_along_path(path0, t0, GLYPH_ADVANCE_EM)
        else:
            x, y = path1(t1)
            rot = _tangent_angle_deg(path1, t1) if rotate else 0.0
            glyphs.append(LayoutGlyph(c, x, y, rot))
            t1 = _advance_along_path(path1, t1, GLYPH_ADVANCE_EM)
    return glyphs


def _layout_figure8(chars: list[str], params: dict) -> list[LayoutGlyph]:
    """
    Figure-eight path (lemniscate of Bernoulli).
    x = a·cos(t)/(1+sin²t), y = a·sin(t)cos(t)/(1+sin²t)
    Params: {scale_em, rotate_chars}.
    """
    a = float(params.get('scale_em', 7))
    rotate = bool(params.get('rotate_chars', True))

    def path(t: float) -> tuple[float, float]:
        s2 = math.sin(t) ** 2
        denom = 1 + s2
        return a * math.cos(t) / denom, a * math.sin(t) * math.cos(t) / denom

    glyphs: list[LayoutGlyph] = []
    t = 0.0
    for c in chars:
        x, y = path(t)
        rot = _tangent_angle_deg(path, t) if rotate else 0.0
        glyphs.append(LayoutGlyph(c, x, y, rot))
        t = _advance_along_path(path, t, GLYPH_ADVANCE_EM)
    return glyphs


def _layout_s_curve(chars: list[str], params: dict) -> list[LayoutGlyph]:
    """
    Smooth S-curve: one full period of a sine wave, chars run nose-to-tail.
    Params: {amplitude_em, length_em, rotate_chars}.
    """
    amp = float(params.get('amplitude_em', 3))
    length = float(params.get('length_em', 16))
    rotate = bool(params.get('rotate_chars', True))
    freq = 2 * math.pi / length  # exactly one full sine period over *length_em*

    def path(x: float) -> tuple[float, float]:
        return x, amp * math.sin(freq * x)

    glyphs: list[LayoutGlyph] = []
    t = 0.0
    for c in chars:
        x, y = path(t)
        rot = _tangent_angle_deg(path, t) if rotate else 0.0
        glyphs.append(LayoutGlyph(c, x, y, rot))
        t = _advance_along_path(path, t, GLYPH_ADVANCE_EM)
    return glyphs


def _layout_dna(chars: list[str], params: dict) -> list[LayoutGlyph]:
    """
    DNA double helix: two phase-shifted sinusoidal strands with cross-bars.
    Params: {amplitude_em, frequency, rung_every, rotate_chars}.
    rung_every = insert a cross-bar glyph (from *chars*) every N chars per strand.
    """
    amp = float(params.get('amplitude_em', 2.0))
    freq = float(params.get('frequency', 1.5)) * math.pi / 10
    rung_every = max(2, int(params.get('rung_every', 5)))
    rotate = bool(params.get('rotate_chars', True))

    def strand_a(x: float) -> tuple[float, float]:
        return x,  amp * math.sin(freq * x)

    def strand_b(x: float) -> tuple[float, float]:
        return x,  amp * math.sin(freq * x + math.pi)

    def rung_path(x: float) -> tuple[float, float]:
        ya = amp * math.sin(freq * x)
        yb = amp * math.sin(freq * x + math.pi)
        return x, (ya + yb) / 2  # midpoint between strands

    glyphs: list[LayoutGlyph] = []
    ta, tb = 0.0, 0.0
    pos_in_strand = 0
    i = 0
    while i < len(chars):
        # Place one glyph on each strand, then optionally a rung
        if i < len(chars):
            x, y = strand_a(ta)
            rot = _tangent_angle_deg(strand_a, ta) if rotate else 0.0
            glyphs.append(LayoutGlyph(chars[i], x, y, rot))
            ta = _advance_along_path(strand_a, ta, GLYPH_ADVANCE_EM)
            i += 1
        if i < len(chars):
            x, y = strand_b(tb)
            rot = _tangent_angle_deg(strand_b, tb) if rotate else 0.0
            glyphs.append(LayoutGlyph(chars[i], x, y, rot))
            tb = _advance_along_path(strand_b, tb, GLYPH_ADVANCE_EM)
            i += 1
        pos_in_strand += 1
        if pos_in_strand % rung_every == 0 and i < len(chars):
            # Cross-bar at midpoint between strands at current ta
            x_r = (ta + tb) / 2
            x, y = rung_path(x_r)
            glyphs.append(LayoutGlyph(chars[i], x, y, 90.0))  # vertical rung
            i += 1
    return glyphs


# ---------------------------------------------------------------------------
# Extended layout library — SHAPE group
# ---------------------------------------------------------------------------

def _layout_triangle_up(chars: list[str], params: dict) -> list[LayoutGlyph]:
    """Equilateral triangle outline (point up). Params: {radius_em, rotate_chars}."""
    r = float(params.get('radius_em', 8))
    rotate = bool(params.get('rotate_chars', True))
    verts = _regular_polygon_vertices(3, r, start_deg=-90.0)
    return _walk_polygon_path(verts, chars, rotate=rotate)


def _layout_triangle_down(chars: list[str], params: dict) -> list[LayoutGlyph]:
    """Equilateral triangle outline (point down). Params: {radius_em, rotate_chars}."""
    r = float(params.get('radius_em', 8))
    rotate = bool(params.get('rotate_chars', True))
    verts = _regular_polygon_vertices(3, r, start_deg=90.0)
    return _walk_polygon_path(verts, chars, rotate=rotate)


def _layout_diamond_outline(chars: list[str], params: dict) -> list[LayoutGlyph]:
    """Diamond / rotated-square outline. Params: {radius_em, rotate_chars}."""
    r = float(params.get('radius_em', 7))
    rotate = bool(params.get('rotate_chars', True))
    verts = _regular_polygon_vertices(4, r, start_deg=-90.0)
    return _walk_polygon_path(verts, chars, rotate=rotate)


def _layout_cross(chars: list[str], params: dict) -> list[LayoutGlyph]:
    """
    Plus-sign / cross shape. Perimeter is the 12-vertex outline of a cross.
    Params: {arm_len_em, arm_width_em, rotate_chars}.
    """
    arm = float(params.get('arm_len_em', 6))
    half = float(params.get('arm_width_em', 1.5))
    rotate = bool(params.get('rotate_chars', True))
    # 12-vertex perimeter of a cross (CW from top-left of top arm)
    verts = [
        (-half, -arm - half),  # top-left of top arm top
        ( half, -arm - half),
        ( half, -half),
        ( arm + half, -half),  # right arm right-top
        ( arm + half,  half),
        ( half,  half),
        ( half,  arm + half),  # bottom arm bottom-right
        (-half,  arm + half),
        (-half,  half),
        (-arm - half,  half),  # left arm left-bottom
        (-arm - half, -half),
        (-half, -half),
    ]
    return _walk_polygon_path(verts, chars, rotate=rotate)


def _layout_star_5(chars: list[str], params: dict) -> list[LayoutGlyph]:
    """Five-pointed star outline. Params: {outer_radius_em, inner_radius_em, rotate_chars}."""
    r_out = float(params.get('outer_radius_em', 9))
    r_in = float(params.get('inner_radius_em', 4))
    rotate = bool(params.get('rotate_chars', True))
    verts = _star_vertices(5, r_out, r_in, start_deg=-90.0)
    return _walk_polygon_path(verts, chars, rotate=rotate)


def _layout_star_6(chars: list[str], params: dict) -> list[LayoutGlyph]:
    """Six-pointed star (Star of David) outline. Params: {outer_radius_em, inner_radius_em, rotate_chars}."""
    r_out = float(params.get('outer_radius_em', 9))
    r_in = float(params.get('inner_radius_em', 5))
    rotate = bool(params.get('rotate_chars', True))
    verts = _star_vertices(6, r_out, r_in, start_deg=-90.0)
    return _walk_polygon_path(verts, chars, rotate=rotate)


def _layout_hexagon(chars: list[str], params: dict) -> list[LayoutGlyph]:
    """Regular hexagon outline. Params: {radius_em, rotate_chars}."""
    r = float(params.get('radius_em', 8))
    rotate = bool(params.get('rotate_chars', True))
    verts = _regular_polygon_vertices(6, r, start_deg=0.0)
    return _walk_polygon_path(verts, chars, rotate=rotate)


def _layout_pentagon(chars: list[str], params: dict) -> list[LayoutGlyph]:
    """Regular pentagon outline. Params: {radius_em, rotate_chars}."""
    r = float(params.get('radius_em', 8))
    rotate = bool(params.get('rotate_chars', True))
    verts = _regular_polygon_vertices(5, r, start_deg=-90.0)
    return _walk_polygon_path(verts, chars, rotate=rotate)


def _layout_heart(chars: list[str], params: dict) -> list[LayoutGlyph]:
    """
    Heart curve (parametric). Chars spaced by arc length.
    Params: {scale_em, rotate_chars}.
    """
    scale = float(params.get('scale_em', 0.5))
    rotate = bool(params.get('rotate_chars', True))

    def path(t: float) -> tuple[float, float]:
        # Classic parametric heart; t ∈ [0, 2π] traces the full heart.
        x = 16 * math.sin(t) ** 3
        y = -(13 * math.cos(t) - 5 * math.cos(2 * t)
               - 2 * math.cos(3 * t) - math.cos(4 * t))
        return x * scale, y * scale

    glyphs: list[LayoutGlyph] = []
    t = 0.0
    for c in chars:
        x, y = path(t)
        rot = _tangent_angle_deg(path, t) if rotate else 0.0
        glyphs.append(LayoutGlyph(c, x, y, rot))
        t = _advance_along_path(path, t, GLYPH_ADVANCE_EM)
    return glyphs


def _layout_infinity(chars: list[str], params: dict) -> list[LayoutGlyph]:
    """
    Infinity symbol / lemniscate of Bernoulli.
    Params: {scale_em, rotate_chars}.
    """
    # Lemniscate: r² = a²·cos(2θ) — parametrise by t
    a = float(params.get('scale_em', 7))
    rotate = bool(params.get('rotate_chars', True))

    def path(t: float) -> tuple[float, float]:
        # Cartesian form: x=a·√2·cos(t)/(sin²t+1), y=a·√2·sin(t)cos(t)/(sin²t+1)
        denom = math.sin(t) ** 2 + 1
        x = a * math.sqrt(2) * math.cos(t) / denom
        y = a * math.sqrt(2) * math.sin(t) * math.cos(t) / denom
        return x, y

    glyphs: list[LayoutGlyph] = []
    t = 0.0
    for c in chars:
        x, y = path(t)
        rot = _tangent_angle_deg(path, t) if rotate else 0.0
        glyphs.append(LayoutGlyph(c, x, y, rot))
        t = _advance_along_path(path, t, GLYPH_ADVANCE_EM)
    return glyphs


def _layout_crescent(chars: list[str], params: dict) -> list[LayoutGlyph]:
    """
    Crescent moon: chars walk the outer arc of a crescent shape.
    Params: {radius_em, span_deg, rotate_chars}.
    """
    r = float(params.get('radius_em', 8))
    span = float(params.get('span_deg', 240))
    rotate = bool(params.get('rotate_chars', True))
    start_deg = -90 - span / 2

    def path(t: float) -> tuple[float, float]:
        return r * math.cos(t), r * math.sin(t)

    glyphs: list[LayoutGlyph] = []
    t = math.radians(start_deg)
    arc_max = abs(math.radians(span)) * r
    arc_used = 0.0
    for c in chars:
        if arc_used >= arc_max:
            break
        x, y = path(t)
        rot = _tangent_angle_deg(path, t) if rotate else 0.0
        glyphs.append(LayoutGlyph(c, x, y, rot))
        t = _advance_along_path(path, t, GLYPH_ADVANCE_EM)
        arc_used += GLYPH_ADVANCE_EM
    return glyphs


# ---------------------------------------------------------------------------
# Extended layout library — BODY group (tattoo-placement-specific)
# ---------------------------------------------------------------------------

def _layout_sleeve_band(chars: list[str], params: dict) -> list[LayoutGlyph]:
    """
    Horizontal sleeve-band: single very-wide row (no wrapping cap by default).
    Chars fit on one long strip; wraps to next row only when row_chars is set.
    Params: {row_chars, line_height_em}.
    row_chars=0 means no wrap (all chars on one row).
    """
    row_chars = int(params.get('row_chars', 0))
    if row_chars < 1:
        row_chars = max(1, len(chars))  # 0 → single row
    line_h = float(params.get('line_height_em', 1.4))
    glyphs: list[LayoutGlyph] = []
    for i, c in enumerate(chars):
        col = i % row_chars
        row = i // row_chars
        glyphs.append(LayoutGlyph(c, col * GLYPH_ADVANCE_EM, row * line_h, 0.0))
    return glyphs


def _layout_spine_col(chars: list[str], params: dict) -> list[LayoutGlyph]:
    """
    Spine column: single vertical column with tight spacing, ideal for back/spine.
    Params: {line_height_em}.
    """
    line_h = float(params.get('line_height_em', 1.1))
    return [LayoutGlyph(c, 0.0, i * line_h, 0.0) for i, c in enumerate(chars)]


def _layout_bracelet(chars: list[str], params: dict) -> list[LayoutGlyph]:
    """
    Bracelet / tight ring for wrist or ankle. Small default radius.
    Params: {radius_em, start_angle_deg, rotate_chars, clockwise}.
    """
    p = dict(params)
    p.setdefault('radius_em', 3.5)
    p.setdefault('start_angle_deg', -90)
    p.setdefault('rotate_chars', True)
    p.setdefault('clockwise', True)
    return _layout_circle(chars, p)


def _layout_shoulder_arc(chars: list[str], params: dict) -> list[LayoutGlyph]:
    """
    Wide shoulder/collarbone arc. Large radius, wide angular span.
    Params: {radius_em, span_deg, start_angle_deg, rotate_chars}.
    """
    p = dict(params)
    p.setdefault('radius_em', 14)
    p.setdefault('span_deg', 140)
    p.setdefault('start_angle_deg', -160)
    p.setdefault('rotate_chars', True)
    return _layout_arc(chars, p)


# ---------------------------------------------------------------------------
# Layout catalog — full library (5 MVP + 35 extended)
# ---------------------------------------------------------------------------

LAYOUT_CATALOG: dict[str, dict] = {

    # ── LINEAR ────────────────────────────────────────────────────────────────
    'paragraph': {
        'label': 'Paragraph',
        'group': 'linear',
        'function': _layout_paragraph,
        'defaults': {'width_chars': 24, 'line_height_em': 1.4},
        'param_schema': {
            'width_chars':    {'type': 'int',   'min': 4, 'max': 80, 'step': 1,
                               'label': 'Characters per line'},
            'line_height_em': {'type': 'float', 'min': 1.0, 'max': 3.0, 'step': 0.1,
                               'label': 'Line height (em)'},
        },
        'text_exportable': True,
    },
    'column_multi': {
        'label': 'Multi-column',
        'group': 'linear',
        'function': _layout_column_multi,
        'defaults': {'columns': 4, 'col_spacing_em': 1.2, 'direction': 'down'},
        'param_schema': {
            'columns':        {'type': 'int',   'min': 1, 'max': 16, 'step': 1,
                               'label': 'Number of columns'},
            'col_spacing_em': {'type': 'float', 'min': 0.5, 'max': 3.0, 'step': 0.1,
                               'label': 'Column spacing (em)'},
            'direction':      {'type': 'enum',  'values': ['down', 'up'],
                               'label': 'Read direction'},
        },
        'text_exportable': True,
    },
    'column_single': {
        'label': 'Single column',
        'group': 'linear',
        'function': _layout_column_single,
        'defaults': {'line_height_em': 1.4},
        'param_schema': {
            'line_height_em': {'type': 'float', 'min': 1.0, 'max': 3.0, 'step': 0.1,
                               'label': 'Line height (em)'},
        },
        'text_exportable': True,
    },
    'boustrophedon': {
        'label': 'Snake / ox-plow',
        'group': 'linear',
        'function': _layout_boustrophedon,
        'defaults': {'width_chars': 20, 'line_height_em': 1.4},
        'param_schema': {
            'width_chars':    {'type': 'int',   'min': 4, 'max': 80, 'step': 1,
                               'label': 'Characters per row'},
            'line_height_em': {'type': 'float', 'min': 1.0, 'max': 3.0, 'step': 0.1,
                               'label': 'Row height (em)'},
        },
        'text_exportable': True,
    },
    'border_rect': {
        'label': 'Rectangle border',
        'group': 'linear',
        'function': _layout_border_rect,
        'defaults': {'width_chars': 20, 'height_chars': 12, 'rotate_chars': True},
        'param_schema': {
            'width_chars':  {'type': 'int',  'min': 4, 'max': 60, 'step': 1,
                             'label': 'Width (chars)'},
            'height_chars': {'type': 'int',  'min': 4, 'max': 40, 'step': 1,
                             'label': 'Height (chars)'},
            'rotate_chars': {'type': 'bool', 'label': 'Rotate glyphs to follow edge'},
        },
        'text_exportable': False,
    },
    'stagger': {
        'label': 'Staggered rows',
        'group': 'linear',
        'function': _layout_stagger,
        'defaults': {'width_chars': 20, 'line_height_em': 1.4},
        'param_schema': {
            'width_chars':    {'type': 'int',   'min': 4, 'max': 80, 'step': 1,
                               'label': 'Characters per row'},
            'line_height_em': {'type': 'float', 'min': 1.0, 'max': 3.0, 'step': 0.1,
                               'label': 'Row height (em)'},
        },
        'text_exportable': True,
    },
    'grid_fill': {
        'label': 'Dense grid',
        'group': 'linear',
        'function': _layout_grid_fill,
        'defaults': {'width_chars': 24, 'row_spacing_em': 1.0},
        'param_schema': {
            'width_chars':    {'type': 'int',   'min': 4, 'max': 80, 'step': 1,
                               'label': 'Characters per row'},
            'row_spacing_em': {'type': 'float', 'min': 0.8, 'max': 2.0, 'step': 0.1,
                               'label': 'Row spacing (em)'},
        },
        'text_exportable': True,
    },
    'pyramid_up': {
        'label': 'Pyramid ▲',
        'group': 'linear',
        'function': _layout_pyramid_up,
        'defaults': {'line_height_em': 1.4},
        'param_schema': {
            'line_height_em': {'type': 'float', 'min': 1.0, 'max': 3.0, 'step': 0.1,
                               'label': 'Row height (em)'},
        },
        'text_exportable': True,
    },
    'pyramid_down': {
        'label': 'Pyramid ▼',
        'group': 'linear',
        'function': _layout_pyramid_down,
        'defaults': {'line_height_em': 1.4},
        'param_schema': {
            'max_width_chars': {'type': 'int', 'min': 0, 'max': 40, 'step': 1,
                                'label': 'Max row width (0 = auto)'},
            'line_height_em':  {'type': 'float', 'min': 1.0, 'max': 3.0, 'step': 0.1,
                                'label': 'Row height (em)'},
        },
        'text_exportable': True,
    },
    'hourglass': {
        'label': 'Hourglass',
        'group': 'linear',
        'function': _layout_hourglass,
        'defaults': {'line_height_em': 1.4},
        'param_schema': {
            'line_height_em': {'type': 'float', 'min': 1.0, 'max': 3.0, 'step': 0.1,
                               'label': 'Row height (em)'},
        },
        'text_exportable': True,
    },
    'diamond_fill': {
        'label': 'Diamond fill ◆',
        'group': 'linear',
        'function': _layout_diamond_fill,
        'defaults': {'line_height_em': 1.4},
        'param_schema': {
            'line_height_em': {'type': 'float', 'min': 1.0, 'max': 3.0, 'step': 0.1,
                               'label': 'Row height (em)'},
        },
        'text_exportable': True,
    },

    # ── RADIAL ────────────────────────────────────────────────────────────────
    'circle': {
        'label': 'Circle',
        'group': 'radial',
        'function': _layout_circle,
        'defaults': {'radius_em': 8, 'start_angle_deg': -90,
                     'rotate_chars': True, 'clockwise': True},
        'param_schema': {
            'radius_em':       {'type': 'float', 'min': 2, 'max': 30, 'step': 0.5,
                                'label': 'Radius (em)'},
            'start_angle_deg': {'type': 'float', 'min': -180, 'max': 180, 'step': 5,
                                'label': 'Start angle (°)'},
            'rotate_chars':    {'type': 'bool', 'label': 'Rotate glyphs to follow curve'},
            'clockwise':       {'type': 'bool', 'label': 'Clockwise'},
        },
        'text_exportable': False,
    },
    'arc': {
        'label': 'Arc',
        'group': 'radial',
        'function': _layout_arc,
        'defaults': {'radius_em': 8, 'start_angle_deg': -120,
                     'span_deg': 240, 'rotate_chars': True, 'clockwise': True},
        'param_schema': {
            'radius_em':       {'type': 'float', 'min': 2, 'max': 30, 'step': 0.5,
                                'label': 'Radius (em)'},
            'start_angle_deg': {'type': 'float', 'min': -180, 'max': 180, 'step': 5,
                                'label': 'Start angle (°)'},
            'span_deg':        {'type': 'float', 'min': 10, 'max': 359, 'step': 5,
                                'label': 'Arc span (°)'},
            'rotate_chars':    {'type': 'bool', 'label': 'Rotate glyphs to follow curve'},
        },
        'text_exportable': False,
    },
    'spiral_inward': {
        'label': 'Spiral (inward)',
        'group': 'radial',
        'function': _layout_spiral_inward,
        'defaults': {'start_radius_em': 10, 'end_radius_em': 2,
                     'start_angle_deg': 0, 'rotate_chars': True},
        'param_schema': {
            'start_radius_em': {'type': 'float', 'min': 3, 'max': 30, 'step': 0.5,
                                'label': 'Outer radius (em)'},
            'end_radius_em':   {'type': 'float', 'min': 0.5, 'max': 10, 'step': 0.5,
                                'label': 'Inner radius (em)'},
            'start_angle_deg': {'type': 'float', 'min': -180, 'max': 180, 'step': 5,
                                'label': 'Start angle (°)'},
            'rotate_chars':    {'type': 'bool', 'label': 'Rotate glyphs to follow curve'},
        },
        'text_exportable': False,
    },
    'spiral_outward': {
        'label': 'Spiral (outward)',
        'group': 'radial',
        'function': _layout_spiral_outward,
        'defaults': {'start_radius_em': 2, 'end_radius_em': 10,
                     'start_angle_deg': 0, 'rotate_chars': True},
        'param_schema': {
            'start_radius_em': {'type': 'float', 'min': 0.5, 'max': 10, 'step': 0.5,
                                'label': 'Inner radius (em)'},
            'end_radius_em':   {'type': 'float', 'min': 3, 'max': 30, 'step': 0.5,
                                'label': 'Outer radius (em)'},
            'start_angle_deg': {'type': 'float', 'min': -180, 'max': 180, 'step': 5,
                                'label': 'Start angle (°)'},
            'rotate_chars':    {'type': 'bool', 'label': 'Rotate glyphs to follow curve'},
        },
        'text_exportable': False,
    },
    'concentric': {
        'label': 'Concentric rings',
        'group': 'radial',
        'function': _layout_concentric,
        'defaults': {'inner_radius_em': 3, 'ring_spacing_em': 1.5,
                     'start_angle_deg': -90, 'rotate_chars': True},
        'param_schema': {
            'inner_radius_em': {'type': 'float', 'min': 1, 'max': 15, 'step': 0.5,
                                'label': 'Inner radius (em)'},
            'ring_spacing_em': {'type': 'float', 'min': 0.5, 'max': 5, 'step': 0.25,
                                'label': 'Spacing between rings (em)'},
            'start_angle_deg': {'type': 'float', 'min': -180, 'max': 180, 'step': 5,
                                'label': 'Start angle (°)'},
            'rotate_chars':    {'type': 'bool', 'label': 'Rotate glyphs to follow curve'},
        },
        'text_exportable': False,
    },
    'double_ring': {
        'label': 'Double ring',
        'group': 'radial',
        'function': _layout_double_ring,
        'defaults': {'inner_radius_em': 5, 'outer_radius_em': 8,
                     'start_angle_deg': -90, 'rotate_chars': True},
        'param_schema': {
            'inner_radius_em': {'type': 'float', 'min': 1, 'max': 15, 'step': 0.5,
                                'label': 'Inner ring radius (em)'},
            'outer_radius_em': {'type': 'float', 'min': 3, 'max': 30, 'step': 0.5,
                                'label': 'Outer ring radius (em)'},
            'start_angle_deg': {'type': 'float', 'min': -180, 'max': 180, 'step': 5,
                                'label': 'Start angle (°)'},
            'rotate_chars':    {'type': 'bool', 'label': 'Rotate glyphs to follow curve'},
        },
        'text_exportable': False,
    },
    'radial_spokes': {
        'label': 'Radial spokes',
        'group': 'radial',
        'function': _layout_radial_spokes,
        'defaults': {'spokes': 8, 'radius_em': 8, 'rotate_chars': True},
        'param_schema': {
            'spokes':       {'type': 'int',   'min': 2, 'max': 24, 'step': 1,
                             'label': 'Number of spokes'},
            'radius_em':    {'type': 'float', 'min': 2, 'max': 20, 'step': 0.5,
                             'label': 'Spoke length (em)'},
            'rotate_chars': {'type': 'bool', 'label': 'Rotate glyphs along spoke'},
        },
        'text_exportable': False,
    },
    'sunburst': {
        'label': 'Sunburst',
        'group': 'radial',
        'function': _layout_sunburst,
        'defaults': {'spokes': 8, 'outer_radius_em': 9, 'inner_radius_em': 5,
                     'rotate_chars': True},
        'param_schema': {
            'spokes':           {'type': 'int',   'min': 2, 'max': 16, 'step': 1,
                                 'label': 'Long spokes (short spokes = same count)'},
            'outer_radius_em':  {'type': 'float', 'min': 4, 'max': 20, 'step': 0.5,
                                 'label': 'Long spoke length (em)'},
            'inner_radius_em':  {'type': 'float', 'min': 1, 'max': 15, 'step': 0.5,
                                 'label': 'Short spoke length (em)'},
            'rotate_chars':     {'type': 'bool', 'label': 'Rotate glyphs along spoke'},
        },
        'text_exportable': False,
    },

    # ── PATH ─────────────────────────────────────────────────────────────────
    'wave': {
        'label': 'Wave',
        'group': 'path',
        'function': _layout_wave,
        'defaults': {'amplitude_em': 2, 'frequency': 2, 'rotate_chars': True},
        'param_schema': {
            'amplitude_em': {'type': 'float', 'min': 0.5, 'max': 10, 'step': 0.25,
                             'label': 'Amplitude (em)'},
            'frequency':    {'type': 'float', 'min': 0.5, 'max': 6, 'step': 0.25,
                             'label': 'Frequency (cycles per ~10 em)'},
            'rotate_chars': {'type': 'bool', 'label': 'Rotate glyphs to follow curve'},
        },
        'text_exportable': False,
    },
    'zigzag': {
        'label': 'Zigzag',
        'group': 'path',
        'function': _layout_zigzag,
        'defaults': {'amplitude_em': 2.5, 'wavelength_em': 4.0, 'rotate_chars': True},
        'param_schema': {
            'amplitude_em':  {'type': 'float', 'min': 0.5, 'max': 10, 'step': 0.25,
                              'label': 'Amplitude (em)'},
            'wavelength_em': {'type': 'float', 'min': 1.0, 'max': 20, 'step': 0.5,
                              'label': 'Wavelength (em)'},
            'rotate_chars':  {'type': 'bool', 'label': 'Rotate glyphs to follow edge'},
        },
        'text_exportable': False,
    },
    'double_wave': {
        'label': 'Double wave',
        'group': 'path',
        'function': _layout_double_wave,
        'defaults': {'amplitude_em': 1.5, 'frequency': 2,
                     'strand_gap_em': 1.2, 'rotate_chars': True},
        'param_schema': {
            'amplitude_em':  {'type': 'float', 'min': 0.5, 'max': 8, 'step': 0.25,
                              'label': 'Amplitude (em)'},
            'frequency':     {'type': 'float', 'min': 0.5, 'max': 6, 'step': 0.25,
                              'label': 'Frequency'},
            'strand_gap_em': {'type': 'float', 'min': 0.5, 'max': 4, 'step': 0.25,
                              'label': 'Gap between strands (em)'},
            'rotate_chars':  {'type': 'bool', 'label': 'Rotate glyphs to follow curve'},
        },
        'text_exportable': False,
    },
    'figure8': {
        'label': 'Figure-eight ∞',
        'group': 'path',
        'function': _layout_figure8,
        'defaults': {'scale_em': 7, 'rotate_chars': True},
        'param_schema': {
            'scale_em':     {'type': 'float', 'min': 2, 'max': 20, 'step': 0.5,
                             'label': 'Scale (em)'},
            'rotate_chars': {'type': 'bool', 'label': 'Rotate glyphs to follow curve'},
        },
        'text_exportable': False,
    },
    's_curve': {
        'label': 'S-curve',
        'group': 'path',
        'function': _layout_s_curve,
        'defaults': {'amplitude_em': 3, 'length_em': 16, 'rotate_chars': True},
        'param_schema': {
            'amplitude_em': {'type': 'float', 'min': 0.5, 'max': 10, 'step': 0.25,
                             'label': 'Amplitude (em)'},
            'length_em':    {'type': 'float', 'min': 4, 'max': 40, 'step': 1,
                             'label': 'Total length (em)'},
            'rotate_chars': {'type': 'bool', 'label': 'Rotate glyphs to follow curve'},
        },
        'text_exportable': False,
    },
    'dna': {
        'label': 'DNA helix',
        'group': 'path',
        'function': _layout_dna,
        'defaults': {'amplitude_em': 2.0, 'frequency': 1.5,
                     'rung_every': 5, 'rotate_chars': True},
        'param_schema': {
            'amplitude_em': {'type': 'float', 'min': 0.5, 'max': 6, 'step': 0.25,
                             'label': 'Amplitude (em)'},
            'frequency':    {'type': 'float', 'min': 0.5, 'max': 4, 'step': 0.25,
                             'label': 'Helix frequency'},
            'rung_every':   {'type': 'int',   'min': 2, 'max': 20, 'step': 1,
                             'label': 'Cross-bar every N strand chars'},
            'rotate_chars': {'type': 'bool', 'label': 'Rotate glyphs to follow curve'},
        },
        'text_exportable': False,
    },

    # ── SHAPE ─────────────────────────────────────────────────────────────────
    'triangle_up': {
        'label': 'Triangle ▲',
        'group': 'shape',
        'function': _layout_triangle_up,
        'defaults': {'radius_em': 8, 'rotate_chars': True},
        'param_schema': {
            'radius_em':    {'type': 'float', 'min': 2, 'max': 20, 'step': 0.5,
                             'label': 'Circumradius (em)'},
            'rotate_chars': {'type': 'bool', 'label': 'Rotate glyphs to follow edge'},
        },
        'text_exportable': False,
    },
    'triangle_down': {
        'label': 'Triangle ▼',
        'group': 'shape',
        'function': _layout_triangle_down,
        'defaults': {'radius_em': 8, 'rotate_chars': True},
        'param_schema': {
            'radius_em':    {'type': 'float', 'min': 2, 'max': 20, 'step': 0.5,
                             'label': 'Circumradius (em)'},
            'rotate_chars': {'type': 'bool', 'label': 'Rotate glyphs to follow edge'},
        },
        'text_exportable': False,
    },
    'diamond_outline': {
        'label': 'Diamond ◇',
        'group': 'shape',
        'function': _layout_diamond_outline,
        'defaults': {'radius_em': 7, 'rotate_chars': True},
        'param_schema': {
            'radius_em':    {'type': 'float', 'min': 2, 'max': 20, 'step': 0.5,
                             'label': 'Half-diagonal (em)'},
            'rotate_chars': {'type': 'bool', 'label': 'Rotate glyphs to follow edge'},
        },
        'text_exportable': False,
    },
    'cross': {
        'label': 'Cross +',
        'group': 'shape',
        'function': _layout_cross,
        'defaults': {'arm_len_em': 6, 'arm_width_em': 1.5, 'rotate_chars': True},
        'param_schema': {
            'arm_len_em':   {'type': 'float', 'min': 1, 'max': 16, 'step': 0.5,
                             'label': 'Arm length (em)'},
            'arm_width_em': {'type': 'float', 'min': 0.5, 'max': 6, 'step': 0.25,
                             'label': 'Arm half-width (em)'},
            'rotate_chars': {'type': 'bool', 'label': 'Rotate glyphs to follow edge'},
        },
        'text_exportable': False,
    },
    'star_5': {
        'label': 'Star ★',
        'group': 'shape',
        'function': _layout_star_5,
        'defaults': {'outer_radius_em': 9, 'inner_radius_em': 4, 'rotate_chars': True},
        'param_schema': {
            'outer_radius_em': {'type': 'float', 'min': 3, 'max': 20, 'step': 0.5,
                                'label': 'Outer radius (em)'},
            'inner_radius_em': {'type': 'float', 'min': 1, 'max': 10, 'step': 0.5,
                                'label': 'Inner radius (em)'},
            'rotate_chars':    {'type': 'bool', 'label': 'Rotate glyphs to follow edge'},
        },
        'text_exportable': False,
    },
    'star_6': {
        'label': 'Star of David ✡',
        'group': 'shape',
        'function': _layout_star_6,
        'defaults': {'outer_radius_em': 9, 'inner_radius_em': 5, 'rotate_chars': True},
        'param_schema': {
            'outer_radius_em': {'type': 'float', 'min': 3, 'max': 20, 'step': 0.5,
                                'label': 'Outer radius (em)'},
            'inner_radius_em': {'type': 'float', 'min': 2, 'max': 12, 'step': 0.5,
                                'label': 'Inner radius (em)'},
            'rotate_chars':    {'type': 'bool', 'label': 'Rotate glyphs to follow edge'},
        },
        'text_exportable': False,
    },
    'hexagon': {
        'label': 'Hexagon ⬡',
        'group': 'shape',
        'function': _layout_hexagon,
        'defaults': {'radius_em': 8, 'rotate_chars': True},
        'param_schema': {
            'radius_em':    {'type': 'float', 'min': 2, 'max': 20, 'step': 0.5,
                             'label': 'Circumradius (em)'},
            'rotate_chars': {'type': 'bool', 'label': 'Rotate glyphs to follow edge'},
        },
        'text_exportable': False,
    },
    'pentagon': {
        'label': 'Pentagon ⬠',
        'group': 'shape',
        'function': _layout_pentagon,
        'defaults': {'radius_em': 8, 'rotate_chars': True},
        'param_schema': {
            'radius_em':    {'type': 'float', 'min': 2, 'max': 20, 'step': 0.5,
                             'label': 'Circumradius (em)'},
            'rotate_chars': {'type': 'bool', 'label': 'Rotate glyphs to follow edge'},
        },
        'text_exportable': False,
    },
    'heart': {
        'label': 'Heart ♥',
        'group': 'shape',
        'function': _layout_heart,
        'defaults': {'scale_em': 0.5, 'rotate_chars': True},
        'param_schema': {
            'scale_em':     {'type': 'float', 'min': 0.2, 'max': 2.0, 'step': 0.05,
                             'label': 'Scale factor'},
            'rotate_chars': {'type': 'bool', 'label': 'Rotate glyphs to follow curve'},
        },
        'text_exportable': False,
    },
    'infinity': {
        'label': 'Infinity ∞',
        'group': 'shape',
        'function': _layout_infinity,
        'defaults': {'scale_em': 7, 'rotate_chars': True},
        'param_schema': {
            'scale_em':     {'type': 'float', 'min': 2, 'max': 20, 'step': 0.5,
                             'label': 'Scale (em)'},
            'rotate_chars': {'type': 'bool', 'label': 'Rotate glyphs to follow curve'},
        },
        'text_exportable': False,
    },
    'crescent': {
        'label': 'Crescent ☽',
        'group': 'shape',
        'function': _layout_crescent,
        'defaults': {'radius_em': 8, 'span_deg': 240, 'rotate_chars': True},
        'param_schema': {
            'radius_em':    {'type': 'float', 'min': 2, 'max': 20, 'step': 0.5,
                             'label': 'Radius (em)'},
            'span_deg':     {'type': 'float', 'min': 60, 'max': 330, 'step': 10,
                             'label': 'Arc span (°)'},
            'rotate_chars': {'type': 'bool', 'label': 'Rotate glyphs to follow curve'},
        },
        'text_exportable': False,
    },

    # ── BODY (tattoo-placement-specific) ──────────────────────────────────────
    'sleeve_band': {
        'label': 'Sleeve band',
        'group': 'body',
        'function': _layout_sleeve_band,
        'defaults': {'row_chars': 0, 'line_height_em': 1.4},
        'param_schema': {
            'row_chars':      {'type': 'int',   'min': 0, 'max': 200, 'step': 1,
                               'label': 'Chars per row (0 = single row)'},
            'line_height_em': {'type': 'float', 'min': 1.0, 'max': 3.0, 'step': 0.1,
                               'label': 'Row height (em)'},
        },
        'text_exportable': True,
    },
    'spine_col': {
        'label': 'Spine column',
        'group': 'body',
        'function': _layout_spine_col,
        'defaults': {'line_height_em': 1.1},
        'param_schema': {
            'line_height_em': {'type': 'float', 'min': 0.8, 'max': 2.5, 'step': 0.05,
                               'label': 'Character spacing (em)'},
        },
        'text_exportable': True,
    },
    'bracelet': {
        'label': 'Bracelet / anklet',
        'group': 'body',
        'function': _layout_bracelet,
        'defaults': {'radius_em': 3.5, 'start_angle_deg': -90,
                     'rotate_chars': True, 'clockwise': True},
        'param_schema': {
            'radius_em':       {'type': 'float', 'min': 1, 'max': 12, 'step': 0.25,
                                'label': 'Radius (em)'},
            'start_angle_deg': {'type': 'float', 'min': -180, 'max': 180, 'step': 5,
                                'label': 'Start angle (°)'},
            'rotate_chars':    {'type': 'bool', 'label': 'Rotate glyphs to follow curve'},
        },
        'text_exportable': False,
    },
    'shoulder_arc': {
        'label': 'Shoulder arc',
        'group': 'body',
        'function': _layout_shoulder_arc,
        'defaults': {'radius_em': 14, 'span_deg': 140,
                     'start_angle_deg': -160, 'rotate_chars': True},
        'param_schema': {
            'radius_em':       {'type': 'float', 'min': 6, 'max': 24, 'step': 0.5,
                                'label': 'Radius (em)'},
            'span_deg':        {'type': 'float', 'min': 60, 'max': 200, 'step': 5,
                                'label': 'Arc span (°)'},
            'start_angle_deg': {'type': 'float', 'min': -180, 'max': 180, 'step': 5,
                                'label': 'Start angle (°)'},
            'rotate_chars':    {'type': 'bool', 'label': 'Rotate glyphs to follow curve'},
        },
        'text_exportable': False,
    },
}


# ---------------------------------------------------------------------------
# Public renderer entry points
# ---------------------------------------------------------------------------

def render_layout(
    encoded_string: str,
    layout_name: str,
    params: dict | None = None,
) -> list[LayoutGlyph]:
    """Resolve *layout_name* in `LAYOUT_CATALOG` and call its function."""
    entry = LAYOUT_CATALOG.get(layout_name)
    if not entry:
        raise ValueError(f'Unknown layout: {layout_name!r}')
    merged = dict(entry['defaults'])
    if params:
        merged.update(params)
    # Strip any combining marks / treat as code-point list. Whitespace
    # in the encoded string is preserved (it occurs in CV1|...|SV1|... headers).
    chars = list(encoded_string)
    return entry['function'](chars, merged)


def bbox_of(glyphs: list[LayoutGlyph]) -> tuple[float, float, float, float]:
    """Return (min_x, min_y, max_x, max_y) in em units. Adds 1 em padding."""
    if not glyphs:
        return (0.0, 0.0, 1.0, 1.0)
    xs = [g.x for g in glyphs]
    ys = [g.y for g in glyphs]
    pad = 1.0
    return (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)


def render_text(glyphs: list[LayoutGlyph], layout_name: str) -> str:
    """
    Plain-text export. Only meaningful for `text_exportable` layouts
    (paragraph, column_multi). For others, returns an explanatory message.

    Algorithm: bin glyphs by rounded y, sort each row by x, concatenate with
    space-padding so columns line up.
    """
    entry = LAYOUT_CATALOG.get(layout_name)
    if not entry or not entry.get('text_exportable'):
        return (f'(Layout "{layout_name}" is not exportable as plain text — '
                f'use SVG or PNG to preserve glyph positions.)')
    if not glyphs:
        return ''
    # Bin by rounded y (line height ≈ 1 em)
    rows: dict[int, list[LayoutGlyph]] = {}
    for g in glyphs:
        key = round(g.y * 1.0)  # 1 em row granularity
        rows.setdefault(key, []).append(g)

    lines: list[str] = []
    min_x = min(g.x for g in glyphs)
    col_width = GLYPH_ADVANCE_EM
    for key in sorted(rows.keys()):
        row = sorted(rows[key], key=lambda g: g.x)
        # Translate to column index from the leftmost glyph
        buf: list[str] = []
        for g in row:
            col = max(0, round((g.x - min_x) / col_width))
            while len(buf) < col:
                buf.append(' ')
            buf.append(g.char)
        lines.append(''.join(buf).rstrip())
    return '\n'.join(lines)


def render_svg(
    glyphs: list[LayoutGlyph],
    *,
    font_size_px: int = 32,
    fg: str = '#0f172a',
    bg: str = 'transparent',
) -> str:
    """
    Self-contained SVG string. Uses the bundled 'Sovereign Mono' font name
    so any HTML page that has the @font-face declaration renders identically;
    standalone viewers will fall back to their nearest monospace.
    """
    if not glyphs:
        return '<svg xmlns="http://www.w3.org/2000/svg"></svg>'

    x0, y0, x1, y1 = bbox_of(glyphs)
    w_em = x1 - x0
    h_em = y1 - y0
    w_px = w_em * font_size_px
    h_px = h_em * font_size_px

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {w_px:.2f} {h_px:.2f}" '
        f'width="{w_px:.0f}" height="{h_px:.0f}">'
    )
    parts.append(
        f'<style>text{{font-family:"Sovereign Mono","DejaVu Sans Mono",'
        f'"Consolas",monospace;font-size:{font_size_px}px;fill:{fg};}}</style>'
    )
    if bg != 'transparent':
        parts.append(f'<rect width="100%" height="100%" fill="{bg}"/>')
    # SVG text baseline is at y; shift glyphs by 0.8·em so they land at the
    # expected centre when caller is thinking visually.
    baseline_shift = 0.35  # em
    for g in glyphs:
        px = (g.x - x0) * font_size_px
        py = (g.y - y0 + baseline_shift) * font_size_px
        # Escape characters that have meaning in SVG text content
        ch = (g.char.replace('&', '&amp;').replace('<', '&lt;')
                    .replace('>', '&gt;').replace('"', '&quot;'))
        if abs(g.rotation_deg) < 0.01:
            parts.append(
                f'<text x="{px:.2f}" y="{py:.2f}" '
                f'text-anchor="middle">{ch}</text>'
            )
        else:
            parts.append(
                f'<text x="{px:.2f}" y="{py:.2f}" text-anchor="middle" '
                f'transform="rotate({g.rotation_deg:.2f} {px:.2f} {py:.2f})">'
                f'{ch}</text>'
            )
    parts.append('</svg>')
    return ''.join(parts)


def glyphs_to_payload(glyphs: list[LayoutGlyph]) -> list[list]:
    """Flatten LayoutGlyph list into a JSON-friendly array for the JS layer."""
    return [[g.char, round(g.x, 4), round(g.y, 4), round(g.rotation_deg, 3)]
            for g in glyphs]


# ---------------------------------------------------------------------------
# PNG renderer (Phase B2) — Pillow-based with the bundled monospace font
# ---------------------------------------------------------------------------

def _bundled_tesseract_path() -> Path | None:
    """
    Return the path to a portable Tesseract install bundled under
    ``<project_root>/bin/tesseract/tesseract.exe``, or None if absent.

    Populated by ``install_tesseract.py``. The same upward-walk strategy as
    the font helper is used so this works under Python and Nuitka builds.
    """
    here = Path(__file__).resolve().parent
    for candidate in (here, here.parent, here.parent.parent):
        target = candidate / 'bin' / 'tesseract' / 'tesseract.exe'
        if target.is_file():
            return target
    return None


def _bundled_tessdata_path() -> Path | None:
    """Return the tessdata folder next to the bundled tesseract.exe, or None."""
    exe = _bundled_tesseract_path()
    if exe is None:
        return None
    td = exe.parent / 'tessdata'
    return td if td.is_dir() else None


def _bundled_font_path() -> Path:
    """
    Locate the bundled DejaVu Sans Mono TTF.

    Resolution walks upward from this module's location until
    ``gui/fonts/DejaVuSansMono.ttf`` is found. This works in three deployment
    modes:

    1. **Source checkout** — module lives at ``<root>/src/sv_tattoo.py``,
       font at ``<root>/gui/fonts/DejaVuSansMono.ttf``. Two levels up.
    2. **Nuitka --standalone** — module and font are co-located inside the
       dist folder. The walk finds the font at the appropriate level
       provided the build uses ``--include-data-dir=gui=gui``.
    3. **Nuitka --onefile** — the bootstrap unpacks to a temp directory.
       ``__file__`` resolves there; same upward-walk strategy applies.
    """
    here = Path(__file__).resolve().parent
    for candidate in (here, here.parent, here.parent.parent):
        target = candidate / 'gui' / 'fonts' / 'DejaVuSansMono.ttf'
        if target.exists():
            return target
    raise FileNotFoundError(
        f'Bundled DejaVu Sans Mono TTF not found. Searched from {here}. '
        f'If running a Nuitka build, ensure --include-data-dir=gui=gui was used.'
    )


# Cached PIL font objects keyed by font_size_px — Pillow's ImageFont objects
# are immutable so safe to share across calls.
_font_cache: dict[int, object] = {}


def _load_font(size_px: int):
    """Return a cached ImageFont.FreeTypeFont for *size_px*. Raises ImportError
    if Pillow is not installed and FileNotFoundError if the bundled font is
    missing.
    """
    if size_px in _font_cache:
        return _font_cache[size_px]
    from PIL import ImageFont  # imported lazily so module import is cheap
    font = ImageFont.truetype(str(_bundled_font_path()), size=size_px)
    _font_cache[size_px] = font
    return font


def render_png(
    glyphs: list[LayoutGlyph],
    out_path: str,
    *,
    font_size_px: int = 32,
    fg: tuple[int, int, int, int] = (15, 23, 42, 255),  # --bg-base hex 0f172a
    bg: tuple[int, int, int, int] | None = None,        # None = transparent
    padding_em: float = 1.0,
) -> tuple[int, int]:
    """
    Rasterise *glyphs* to a PNG file via Pillow.

    Returns (width_px, height_px) of the saved image.

    Rotation handling (per Gemini's watchpoint): each glyph is drawn onto a
    padded intermediate image (3·font_size square) so the visible ink can't
    extend past the bounding box during font rendering. The intermediate is
    rotated with ``expand=True``, then tightly cropped via the alpha channel
    before pasting onto the master. Master uses RGBA mode so anti-aliased
    edges blend cleanly against the background or transparency.
    """
    from PIL import Image, ImageDraw

    if not glyphs:
        # Save a tiny 1x1 transparent PNG so callers get a valid file
        Image.new('RGBA', (1, 1), (0, 0, 0, 0)).save(out_path)
        return (1, 1)

    font = _load_font(font_size_px)

    # Master canvas size from glyph bbox + padding
    x0, y0, x1, y1 = bbox_of(glyphs)
    pad_em = padding_em
    width_em = (x1 - x0) + 2 * pad_em - 2  # bbox_of already adds 1em padding
    height_em = (y1 - y0) + 2 * pad_em - 2
    width_px = max(1, int(math.ceil(width_em * font_size_px)))
    height_px = max(1, int(math.ceil(height_em * font_size_px)))

    bg_rgba = bg if bg is not None else (0, 0, 0, 0)
    master = Image.new('RGBA', (width_px, height_px), bg_rgba)

    # Origin offset: shift so the bbox's top-left lands at (pad_em, pad_em)
    # in em units; convert to pixels.
    origin_x = (-x0 + pad_em - 1) * font_size_px  # -1 to undo bbox_of's pad
    origin_y = (-y0 + pad_em - 1) * font_size_px

    # Glyph render workspace — generous padding to survive rotation
    pad_px = font_size_px * 3
    workspace_size = (pad_px * 2, pad_px * 2)

    for g in glyphs:
        # Draw glyph in the centre of an oversized transparent workspace
        glyph_img = Image.new('RGBA', workspace_size, (0, 0, 0, 0))
        gd = ImageDraw.Draw(glyph_img)
        gd.text(
            (pad_px, pad_px),
            g.char,
            font=font,
            fill=fg,
            anchor='mm',  # middle-middle: position is the visual centre
        )

        # Rotate (negate angle: Pillow is CCW-positive, our convention is CW)
        if abs(g.rotation_deg) > 0.01:
            rotated = glyph_img.rotate(
                -g.rotation_deg,
                resample=Image.Resampling.BICUBIC,
                expand=True,
            )
        else:
            rotated = glyph_img

        # Tight crop via alpha channel — discards transparent margin
        bbox_rect = rotated.getbbox()
        if bbox_rect is None:
            continue  # blank glyph (e.g. space)
        cropped = rotated.crop(bbox_rect)

        # Compute where the glyph's anchor (the original pad_px/pad_px
        # centre) is *inside* the cropped image. After rotate(expand=True)
        # the centre stays at (rotated.width/2, rotated.height/2); the
        # crop shifts that by the bbox's top-left offset.
        cx_in_cropped = rotated.width / 2 - bbox_rect[0]
        cy_in_cropped = rotated.height / 2 - bbox_rect[1]

        target_x = origin_x + g.x * font_size_px
        target_y = origin_y + g.y * font_size_px
        paste_x = int(round(target_x - cx_in_cropped))
        paste_y = int(round(target_y - cy_in_cropped))

        master.alpha_composite(cropped, dest=(paste_x, paste_y))

    master.save(out_path, format='PNG')
    return (width_px, height_px)


# ---------------------------------------------------------------------------
# Recognition adapters (Phase B3) — image-to-text strategies
# ---------------------------------------------------------------------------
# The adapter pattern lets us slot in Tesseract today and a custom Unicode-
# aware glyph matcher in the future (Phase B4) without changing callers.
#
# Every adapter exposes:
#   name            — short id ('manual' / 'tesseract' / 'custom_glyph')
#   label           — human label shown in the GUI
#   available_now() — True if this adapter can run right now
#   reason()        — explanation string when available_now is False
#   recognize(image_path, alphabet_chars='') -> {ok, text, confidence?, error?}

class _ManualAdapter:
    name = 'manual'
    label = 'Manual entry'

    def available_now(self) -> bool:
        return True

    def reason(self) -> str:
        return ''

    def recognize(self, image_path: str, alphabet_chars: str = '') -> dict:
        # Manual mode never recognizes — the user types it. We return an
        # empty string so the side-by-side editor opens with a blank slate.
        return {'ok': True, 'text': '', 'confidence': None}


class _TesseractAdapter:
    name = 'tesseract'
    label = 'Tesseract OCR (ASCII)'

    def __init__(self, tesseract_cmd: str = ''):
        self._cmd = tesseract_cmd  # caller can pre-set from Settings

    def _resolve_cmd(self) -> str:
        """
        Pick a tesseract executable in this priority order:
          1. Bundled portable install at <project_root>/bin/tesseract/tesseract.exe
             (placed by install_tesseract.py — also auto-included by Nuitka builds)
          2. Explicit Settings override (passed in __init__)
          3. shutil.which('tesseract') — system PATH
          4. Common Windows install locations
        Returns '' if none found.
        """
        # 1. Portable bundle
        portable = _bundled_tesseract_path()
        if portable:
            return str(portable)
        # 2. Settings override
        if self._cmd and Path(self._cmd).is_file():
            return self._cmd
        # 3. PATH
        import shutil as _shutil
        found = _shutil.which('tesseract')
        if found:
            return found
        # 4. Common Windows installs
        import os
        candidates = [
            r'C:\Program Files\Tesseract-OCR\tesseract.exe',
            r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
            os.path.expandvars(r'%LOCALAPPDATA%\Tesseract-OCR\tesseract.exe'),
            os.path.expandvars(r'%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe'),
        ]
        for p in candidates:
            if Path(p).is_file():
                return p
        return ''

    def available_now(self) -> bool:
        try:
            import pytesseract  # noqa: F401
        except ImportError:
            return False
        return bool(self._resolve_cmd())

    def reason(self) -> str:
        try:
            import pytesseract  # noqa: F401
        except ImportError:
            return 'pytesseract not installed (pip install pytesseract)'
        if not self._resolve_cmd():
            return ('Tesseract binary not found. Run '
                    '`python scripts/install_tesseract.py` (or double-click '
                    'scripts/install_tesseract.bat) for a portable install, '
                    'use UB-Mannheim\'s installer at '
                    'https://github.com/UB-Mannheim/tesseract/wiki, '
                    'or set the path manually in Settings.')
        return ''

    def recognize(self, image_path: str, alphabet_chars: str = '') -> dict:
        try:
            import pytesseract
        except ImportError as e:
            return {'ok': False, 'error': f'pytesseract missing: {e}'}

        cmd = self._resolve_cmd()
        if not cmd:
            return {'ok': False, 'error': self.reason()}
        pytesseract.pytesseract.tesseract_cmd = cmd

        # When running against the portable bundle, point Tesseract at the
        # bundled tessdata so it finds language files even when no system-
        # wide install exists. Save+restore the env var to avoid leaking.
        import os as _os
        prev_prefix = _os.environ.get('TESSDATA_PREFIX')
        td = _bundled_tessdata_path()
        if td is not None and Path(cmd).resolve() == _bundled_tesseract_path().resolve():
            _os.environ['TESSDATA_PREFIX'] = str(td)

        try:
            from PIL import Image
            img = Image.open(image_path)
        except Exception as e:
            return {'ok': False, 'error': f'Cannot open image: {e}'}

        # If the alphabet is a strict ASCII subset, constrain Tesseract via
        # tessedit_char_whitelist — this significantly improves accuracy.
        config = '--psm 6'  # uniform block of text
        if alphabet_chars and all(ord(c) < 128 for c in alphabet_chars):
            wl = ''.join(sorted(set(alphabet_chars)))
            config += f' -c tessedit_char_whitelist={wl}'

        try:
            text = pytesseract.image_to_string(img, config=config)
        except Exception as e:
            return {'ok': False, 'error': f'Tesseract failed: {e}'}
        finally:
            # Restore TESSDATA_PREFIX exactly as we found it
            if prev_prefix is None:
                _os.environ.pop('TESSDATA_PREFIX', None)
            else:
                _os.environ['TESSDATA_PREFIX'] = prev_prefix

        return {'ok': True, 'text': text.strip(), 'confidence': None}


class _CustomGlyphAdapter:
    """Phase B4 stub. Architecture ready; implementation pending."""
    name = 'custom_glyph'
    label = 'Custom alphabet matcher (planned)'

    def available_now(self) -> bool:
        return False

    def reason(self) -> str:
        return ('Custom alphabet-aware recognition is planned for a future '
                'release. It will template-match against per-alphabet glyph '
                'images, enabling OCR of Unicode symbol alphabets that '
                'Tesseract cannot handle.')

    def recognize(self, image_path: str, alphabet_chars: str = '') -> dict:
        return {'ok': False, 'error': self.reason()}


def list_adapters(tesseract_cmd: str = '') -> list:
    """
    Return all available recognition adapters. *tesseract_cmd* is an optional
    override path from Settings; pass '' to use auto-detection.
    """
    return [
        _ManualAdapter(),
        _TesseractAdapter(tesseract_cmd=tesseract_cmd),
        _CustomGlyphAdapter(),
    ]


def get_adapter(name: str, tesseract_cmd: str = ''):
    """Look up an adapter by name. Returns None if unknown."""
    for a in list_adapters(tesseract_cmd):
        if a.name == name:
            return a
    return None


# ---------------------------------------------------------------------------
# Self-tests (run `python src/sv_tattoo.py`)
# ---------------------------------------------------------------------------

def _self_test() -> None:
    import sys

    failures: list[str] = []

    def check(name: str, cond: bool, detail: str = '') -> None:
        if cond:
            print(f'  ok  {name}')
        else:
            failures.append(name)
            print(f'  FAIL {name}  {detail}')

    print('1. _advance_along_path on a unit circle')
    # path = unit circle; arc length from theta=0 of pi should land at theta=pi
    def unit_circle(theta: float) -> tuple[float, float]:
        return math.cos(theta), math.sin(theta)
    t_pi = _advance_along_path(unit_circle, 0.0, math.pi)
    err = abs(t_pi - math.pi)
    check('half-circumference -> theta=pi', err < 0.001, f'err={err:.6f}')

    # Quarter arc
    t_q = _advance_along_path(unit_circle, 0.0, math.pi / 2)
    err = abs(t_q - math.pi / 2)
    check('quarter-circumference -> theta=pi/2', err < 0.001, f'err={err:.6f}')

    print('2. _advance_along_path on a line -- arc = parametric distance')
    def horizontal(t: float) -> tuple[float, float]:
        return t, 0.0
    t_5 = _advance_along_path(horizontal, 0.0, 5.0)
    err = abs(t_5 - 5.0)
    check('horizontal line, arc 5 -> t=5', err < 0.001, f'err={err:.6f}')

    print('3. Circle layout: 24 chars on r=10, final angle sweep < 2pi')
    chars = list('ABCDEFGHIJKLMNOPQRSTUVWX')
    glyphs = _layout_circle(chars, {'radius_em': 10, 'rotate_chars': True})
    check('produces 24 glyphs', len(glyphs) == 24)
    # Each char should advance ~GLYPH_ADVANCE_EM along the arc.
    # Total arc = 24 * 0.62 = 14.88 em. Circumference = 2π·10 ≈ 62.83. < 2π ✓
    sweep_deg = math.degrees(math.atan2(glyphs[-1].y, glyphs[-1].x) -
                              math.atan2(glyphs[0].y, glyphs[0].x))
    # Should be roughly (24-1) * (0.62 / 10) radians = 1.4 rad ≈ 80°
    expected_sweep = math.degrees(23 * GLYPH_ADVANCE_EM / 10)
    err = abs(abs(sweep_deg) - expected_sweep)
    check('arc sweep matches expected', err < 5,
          f'sweep={sweep_deg:.1f}deg expected~{expected_sweep:.1f}deg')

    print('4. Paragraph layout: 50 chars / width 10 -> 5 rows')
    chars = ['x'] * 50
    glyphs = _layout_paragraph(chars, {'width_chars': 10, 'line_height_em': 1.4})
    max_row = max(g.y for g in glyphs) / 1.4
    check('5 rows (max_y / line_height ~ 4)', round(max_row) == 4, f'max_row={max_row}')

    print('5. Multi-column layout: 12 chars / 3 columns -> 4 rows')
    chars = list('ABCDEFGHIJKL')
    glyphs = _layout_column_multi(chars, {'columns': 3, 'col_spacing_em': 1.2})
    # Chars 0..3 in col 0, 4..7 in col 1, 8..11 in col 2
    check('first char at x=0', glyphs[0].x == 0)
    check('fifth char at x=1.2', abs(glyphs[4].x - 1.2) < 0.01)
    check('ninth char at x=2.4', abs(glyphs[8].x - 2.4) < 0.01)

    print('6. Spiral inward -- final radius approaches end_radius_em')
    chars = ['x'] * 60
    glyphs = _layout_spiral_inward(chars, {'start_radius_em': 10, 'end_radius_em': 2})
    final_r = math.hypot(glyphs[-1].x, glyphs[-1].y)
    initial_r = math.hypot(glyphs[0].x, glyphs[0].y)
    check('initial r ~ 10', abs(initial_r - 10) < 0.5, f'r={initial_r:.2f}')
    check('final r decreases', final_r < initial_r, f'final_r={final_r:.2f}')

    print('7. Wave layout -- y oscillates around 0')
    chars = ['x'] * 40
    glyphs = _layout_wave(chars, {'amplitude_em': 2, 'frequency': 2})
    ys = [g.y for g in glyphs]
    check('y in [-amp, amp]', all(-2.01 <= y <= 2.01 for y in ys))
    check('y changes sign (oscillates)',
          any(ys[i] * ys[i+1] < 0 for i in range(len(ys)-1)))

    print('8. render_layout dispatches by name')
    g = render_layout('Hello tattoo', 'circle', {'radius_em': 5})
    check('len matches input string', len(g) == 12)

    print('9. render_text -- paragraph round-trips')
    chars = list('Sovereign')
    glyphs = _layout_paragraph(chars, {'width_chars': 4})
    out = render_text(glyphs, 'paragraph')
    check('text export has 3 lines for 9 chars / width 4',
          out.count('\n') == 2, f'out={out!r}')

    print('10. render_text -- circle layout returns the "not exportable" note')
    out = render_text(g, 'circle')
    check('returns explanatory message', 'not exportable' in out)

    print('11. render_svg -- produces valid SVG header')
    svg = render_svg(g, font_size_px=24)
    check('starts with <svg>', svg.startswith('<svg'))
    check('contains viewBox',  'viewBox=' in svg)
    check('one text per glyph', svg.count('<text') == len(g))

    print('12. Unicode chars survive the pipeline')
    chars = list('♠♣♥♦αβγ')
    glyphs = _layout_paragraph(chars, {'width_chars': 7})
    check('all chars present', [g.char for g in glyphs] == ['♠','♣','♥','♦','α','β','γ'])

    print()
    if failures:
        print(f'FAILURES: {len(failures)}')
        for f in failures:
            print(f'  - {f}')
        sys.exit(1)
    print('All self-tests passed.')


if __name__ == '__main__':
    _self_test()
