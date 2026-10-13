"""
README:
snap a messy selection onto the smooth shape that best fits it.
(Blender, Edit Mode, run from the Text Editor. Works on the ACTIVE shape 
key, Basis it reshapes the mesh, on a key it reshapes that key.)

SHAPE = "auto" picks one of the below for you
  "curve"   selection is a path of verts (an edge loop / a bevel row):
            least-squares smooth curve through them, by arc length.
            Closed loops get a closed curve (low Fourier terms), open paths a
            polynomial. Ends stay pinned on open paths (KEEP_ENDS).
  "circle"  path -> best-fit circle / arc (perfect round collars, cuffs).
  "surface" anything else (a patch, a bevel strip): best-fit smooth surface
            (polynomial height field over the patch's own plane).

Knobs:
  SMOOTH    curve: how many bends it may have (open: polynomial degree 2-5,
            closed: harmonics 1-4). Lower = smoother.
  DEGREE    surface: 2 = dome / saddle, 3 = one more wiggle.
  STRENGTH  1 = all the way onto the fit, 0.5 = halfway.
  EVEN      curve / circle: also respace the verts evenly along it.
"""
import bpy, bmesh, math
import numpy as np

SHAPE = "auto"      # "auto", "curve", "circle", "surface"
SMOOTH = 3          # 1-5, how many bends a curve may have (lower = smoother)
DEGREE = 2          # polynomial fit
STRENGTH = 1.0      # 0.0 = no fit, 1.0 = all the way onto the fit
EVEN = False
KEEP_ENDS = True    # If False, consider using the native Vertex Smooth function

ob = bpy.context.active_object
assert ob and ob.type == 'MESH' and ob.mode == 'EDIT', "Edit Mode on the mesh, verts selected"
bm = bmesh.from_edit_mesh(ob.data)
bm.verts.ensure_lookup_table()
sel = [v for v in bm.verts if v.select]
assert len(sel) >= 3, "Select at least 3 verts"
S = set(sel)


def paths():
    """Split the selection into connected pieces; return (verts, is_path, closed)."""
    left, out = set(sel), []
    while left:
        start = left.pop(); comp, stack = [start], [start]
        while stack:
            v = stack.pop()
            for e in v.link_edges:
                w = e.other_vert(v)
                if w in left: left.remove(w); comp.append(w); stack.append(w)
        nb = {v: [e.other_vert(v) for e in v.link_edges if e.other_vert(v) in S and e.other_vert(v) in comp] for v in comp}
        is_path = all(len(n) <= 2 for n in nb.values())
        if is_path and len(comp) >= 3:
            ends = [v for v in comp if len(nb[v]) == 1]
            closed = not ends
            cur = ends[0] if ends else comp[0]
            order, prev = [cur], None
            while True:
                nxt = [w for w in nb[cur] if w is not prev and w not in order]
                if not nxt: break
                prev, cur = cur, nxt[0]; order.append(cur)
            out.append((order, True, closed))
        else:
            out.append((comp, False, False))
    return out


def arc_t(P, closed):
    seg = np.linalg.norm(np.diff(np.vstack([P, P[:1]]) if closed else P, axis=0), axis=1)
    t = np.concatenate([[0], np.cumsum(seg)])
    L = t[-1]
    return (t[:len(P)] / L if L > 0 else np.linspace(0, 1, len(P))), L


def fit_curve(P, closed):
    t, _ = arc_t(P, closed)
    if closed:
        h = max(1, min(SMOOTH, 4, (len(P) - 1) // 2))
        def basis(tt): return np.column_stack([np.ones_like(tt)] + [f(2 * math.pi * k * tt) for k in range(1, h + 1) for f in (np.cos, np.sin)])
    else:
        d = max(1, min(SMOOTH, 5, len(P) - 1))
        def basis(tt): return np.column_stack([tt ** k for k in range(d + 1)])
    A = basis(t)
    w = np.ones(len(P))
    if KEEP_ENDS and not closed: w[0] = w[-1] = 1e4            # pin the ends
    C, *_ = np.linalg.lstsq(A * w[:, None], P * w[:, None], rcond=None)
    tt = (np.arange(len(P)) / (len(P) if closed else len(P) - 1)) if EVEN else t
    return basis(tt) @ C


def fit_circle(P, closed):
    c0 = P.mean(0); U, s, Vt = np.linalg.svd(P - c0)
    n = Vt[2]; e1 = Vt[0]; e2 = np.cross(n, e1)
    x, y = (P - c0) @ e1, (P - c0) @ e2
    A = np.column_stack([x, y, np.ones_like(x)])
    (a, b, c), *_ = np.linalg.lstsq(A, x * x + y * y, rcond=None)
    cx, cy = a / 2, b / 2; r = math.sqrt(max(c + cx * cx + cy * cy, 1e-12))
    ang = np.unwrap(np.arctan2(y - cy, x - cx))
    if EVEN:
        if closed: ang = ang[0] + np.arange(len(P)) * 2 * math.pi / len(P) * np.sign(ang[-1] - ang[0] or 1)
        else: ang = np.linspace(ang[0], ang[-1], len(P))
    Q = c0 + np.outer(cx + r * np.cos(ang), e1) + np.outer(cy + r * np.sin(ang), e2)
    if KEEP_ENDS and not closed: Q[0], Q[-1] = P[0], P[-1]
    return Q


def fit_surface(P):
    c0 = P.mean(0); U, s, Vt = np.linalg.svd(P - c0)
    e1, e2, n = Vt[0], Vt[1], Vt[2]
    u, v, h = (P - c0) @ e1, (P - c0) @ e2, (P - c0) @ n
    sc = max(np.abs(u).max(), np.abs(v).max(), 1e-9); u, v = u / sc, v / sc
    terms = [(i, j) for i in range(DEGREE + 1) for j in range(DEGREE + 1 - i)]
    while len(terms) > len(P): terms.pop()
    A = np.column_stack([u ** i * v ** j for i, j in terms])
    C, *_ = np.linalg.lstsq(A, h, rcond=None)
    return P + np.outer(A @ C - h, n)


moved = 0
for verts, is_path, closed in paths():
    P = np.array([v.co[:] for v in verts])
    kind = SHAPE if SHAPE != "auto" else ("curve" if is_path else "surface")
    if kind in ("curve", "circle") and not is_path:
        print(f"  skipped a piece of {len(verts)} verts: not a single path (use surface)"); continue
    Q = fit_curve(P, closed) if kind == "curve" else fit_circle(P, closed) if kind == "circle" else fit_surface(P)
    for v, p, q in zip(verts, P, Q):
        v.co = p + (q - p) * STRENGTH
    moved += len(verts)
    print(f"  {kind}{' (closed)' if closed else ''}: {len(verts)} verts, max move {np.linalg.norm(Q - P, axis=1).max() * STRENGTH:.4f}")

bmesh.update_edit_mesh(ob.data)
print(f"fit_verts: {moved} verts fitted")
