"""
README:
snap a messy selection onto the smooth shape that best fits it.
(Blender, Edit Mode, run from the Text Editor. Works on the ACTIVE shape
key, Basis it reshapes the mesh, on a key it reshapes that key.)

MODE picks the job:
  "shape"     lines and edges (also rings / strips): snap onto a clean
              curve, circle or surface (see SHAPE below)
  "untangle"  bound messes: crumpled / crossed grids. Fits a surface through
              the selection, then slides each vert toward the middle of its
              neighbours while staying on it (RELAX), so the grid evens out.
              Border verts can stay put (PIN_EDGE).
              Select the mess plus a ring of good verts around it.
  "smooth"    flatten and smooth generally: pimples, dents, lumps.
              Select ONLY the bump. The surface is fitted to the untouched
              verts AROUND it (SMOOTH_RINGS) and the bump is pressed back onto
              it (and evened out with RELAX). Nothing outside moves.
  "corner"    a bevelled vertex (one vert that became a small cluster).
              Select ONLY the cluster. It becomes a smooth, curved blend that
              becomes a rounded cap (like a bevel's round profile): a bulge
              in the centre that meets the edges leaving the cluster smoothly.
              Size and sideways position never change - only the height off
              the cluster's rim plane is rebuilt. No knobs.

SHAPE (for MODE = "shape") = "auto" picks one of the below for you
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
  DEGREE    surface / untangle / smooth: 1 = flat plane, 2 = dome / saddle,
            3 = one more wiggle.
  STRENGTH  1 = all the way onto the fit, 0.5 = halfway.
  EVEN      curve / circle: respace the verts equally along the fitted line,
            measured from the endpoints (default on).
  RELAX     untangle / smooth: evening-out passes (0 = only snap onto the surface).
  PIN_EDGE  untangle: border verts stay put (False = they flatten too).
  SMOOTH_RINGS smooth: rings of untouched verts around the bump that define the surface.
"""
import bpy, bmesh, math
import numpy as np

MODE = "untangle"      # "shape", "untangle", "smooth", "corner"
SHAPE = "auto"      # shape mode: "auto", "curve", "circle", "surface"

SMOOTH = 2          # 1-5, how many bends a curve may have (lower = smoother)
DEGREE = 2          # polynomial fit: 1 = flat, 2 = dome / saddle, 3 = one more wiggle
STRENGTH = 1.0      # 0.0 = no fit, 1.0 = all the way onto the fit
EVEN = True         # curve / circle: equal spacing along the fitted line (ends stay put on open paths)
KEEP_ENDS = True    # If False, consider using the native Vertex Smooth function
RELAX = 30          # untangle / smooth: evening-out passes (0 = only snap onto the surface)
PIN_EDGE = True     # untangle: verts on the selection's border stay put (blends into the rest)
SMOOTH_RINGS = 3    # smooth: rings of UNselected verts around the bump that describe the surface

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
    if not EVEN:
        return basis(t) @ C
    # EVEN: equal spacing measured along the FITTED curve itself (exact), from the first vert / endpoints
    dense_t = np.linspace(0.0, 1.0, 2000)
    D = basis(dense_t) @ C
    if closed:
        D = np.vstack([D, D[:1]]); dense_t = np.append(dense_t, 1.0)
    s_ = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(D, axis=0), axis=1))])
    want = np.arange(len(P)) * (s_[-1] / len(P)) if closed else np.linspace(0.0, s_[-1], len(P))
    Q = np.column_stack([np.interp(want, s_, D[:, k]) for k in range(3)])
    if KEEP_ENDS and not closed: Q[0], Q[-1] = P[0], P[-1]
    return Q


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


def surface_fn(P, W=None):
    """Best-fit smooth surface (optionally weighted per point); returns a function that drops points onto it."""
    W = np.ones(len(P)) if W is None else np.asarray(W, float)
    c0 = (P * W[:, None]).sum(0) / W.sum()
    U, s, Vt = np.linalg.svd((P - c0) * np.sqrt(W)[:, None])
    e1, e2, n = Vt[0], Vt[1], Vt[2]
    u, v = (P - c0) @ e1, (P - c0) @ e2
    sc = max(np.abs(u).max(), np.abs(v).max(), 1e-9)
    terms = [(i, j) for i in range(DEGREE + 1) for j in range(DEGREE + 1 - i)]
    while len(terms) > len(P): terms.pop()
    def A(X):
        uu, vv = ((X - c0) @ e1) / sc, ((X - c0) @ e2) / sc
        return np.column_stack([uu ** i * vv ** j for i, j in terms])
    sw = np.sqrt(W)
    C, *_ = np.linalg.lstsq(A(P) * sw[:, None], ((P - c0) @ n) * sw, rcond=None)
    return lambda X: X + np.outer(A(X) @ C - (X - c0) @ n, n)


def fit_surface(P, verts, relax):
    proj = surface_fn(P)
    Q = proj(P)
    if relax <= 0:
        return Q
    # untangle: slide verts toward the middle of their neighbours, staying on the surface.
    # Verts on the selection's edge (touching unselected verts) stay put, so it blends in.
    idx = {v: i for i, v in enumerate(verts)}
    nbr = [[w for w in (e.other_vert(v) for e in v.link_edges)] for v in verts]
    pinned = np.array([any(w not in S for w in nb) for nb in nbr]) if PIN_EDGE else np.zeros(len(verts), bool)
    fixed_pos = {w: np.array(w.co[:]) for nb in nbr for w in nb if w not in idx}
    X = np.where(pinned[:, None], P, Q)
    for _ in range(relax):
        avg = np.array([np.mean([X[idx[w]] if w in idx else fixed_pos[w] for w in nb], axis=0) if nb else X[i]
                        for i, nb in enumerate(nbr)])
        Y = proj(X + (avg - X) * 0.5)
        X = np.where(pinned[:, None], X, Y)
    return X


def smooth(verts, P):
    """Fit the surface to the untouched ring around the bump, press the bump onto it."""
    ring, frontier, seen = [], set(verts), set(verts)
    for _ in range(SMOOTH_RINGS):
        nxt = set()
        for v in frontier:
            for e in v.link_edges:
                w = e.other_vert(v)
                if w not in seen and w not in S: seen.add(w); nxt.add(w); ring.append(w)
        frontier = nxt
    assert len(ring) >= 6, "smooth: not enough untouched verts around the selection"
    proj = surface_fn(np.array([w.co[:] for w in ring]))
    X = proj(P)
    if RELAX > 0:   # even out the smoothed verts, staying on the surface; the ring stays put
        idx = {v: i for i, v in enumerate(verts)}
        nbr = [[e.other_vert(v) for e in v.link_edges] for v in verts]
        for _ in range(RELAX):
            avg = np.array([np.mean([X[idx[w]] if w in idx else np.array(w.co[:]) for w in nb], axis=0) for nb in nbr])
            X = proj(X + (avg - X) * 0.5)
    return X


def corner(verts, P):
    """Bevel corner -> a rounded cap, like a bevel's round profile.
    The cluster's outer verts (the ones with an edge leaving the cluster) set a base plane.
    The edges leaving the cluster set how steeply the cap must meet them; the inside verts
    are lifted into a spherical cap that meets those edges smoothly - a bulge in the centre.
    Every vert keeps its place ACROSS the plane (so the size and the sideways position never
    change); only the height off the plane is rebuilt. Concave corners dip instead of bulge."""
    idx = {v: i for i, v in enumerate(verts)}
    outer = [i for i, v in enumerate(verts) if any(e.other_vert(v) not in idx for e in v.link_edges)]
    assert len(outer) >= 3, "corner: needs at least 3 cluster verts with edges leaving the cluster"
    B = P[outer]
    c = B.mean(axis=0)
    _, _, Vt = np.linalg.svd(B - c)
    e1, e2, n = Vt[0], Vt[1], Vt[2]
    # the edges leaving the cluster: which way do they head, and how steeply?
    dirs = []
    for i in outer:
        v = verts[i]
        for e in v.link_edges:
            w = e.other_vert(v)
            if w not in idx:
                d = np.array(w.co[:]) - P[i]; L = np.linalg.norm(d)
                if L > 1e-12: dirs.append(d / L)
    dirs = np.array(dirs)
    if (dirs @ n).mean() > 0: n = -n                       # n points to the bulge side (away from where the edges go)
    theta = float(np.clip(np.arcsin(np.clip(-(dirs @ n), -1, 1)).mean(), -1.4, 1.4))   # meeting angle (rad)
    u, w = (P - c) @ e1, (P - c) @ e2
    r = np.sqrt(u * u + w * w)
    a = float(np.linalg.norm(B - c, axis=1).mean())        # cap radius = the cluster's own size
    h = np.zeros(len(P))
    if abs(theta) > 1e-4 and a > 1e-12:
        Rs = a / abs(math.sin(theta))                      # sphere that meets the edges at that angle
        rr = np.minimum(r, a)
        h = np.sqrt(np.maximum(Rs * Rs - rr * rr, 0)) - math.sqrt(max(Rs * Rs - a * a, 0))
        h *= math.copysign(1.0, theta)
    h[outer] = 0.0                                         # the rim sits on the base plane
    print(f"    corner: {len(verts)} verts, meets its edges at {math.degrees(theta):.0f} deg, "
          f"bulge {h.max() if theta >= 0 else h.min():.5f}")
    return c + np.outer(u, e1) + np.outer(w, e2) + np.outer(h, n)


assert MODE in ("shape", "untangle", "smooth", "corner"), f"MODE '{MODE}'? use shape / untangle / smooth / corner"
moved = 0
for verts, is_path, closed in paths():
    P = np.array([v.co[:] for v in verts])
    if MODE == "smooth":
        kind, Q = "smooth", smooth(verts, P)
    elif MODE == "corner":
        kind, Q = "corner", corner(verts, P)
    elif MODE == "untangle":
        kind, Q = "untangle", fit_surface(P, verts, RELAX)
    else:
        kind = SHAPE if SHAPE != "auto" else ("curve" if is_path else "surface")
        if kind in ("curve", "circle") and not is_path:
            print(f"  skipped a piece of {len(verts)} verts: not a single path (use surface)"); continue
        Q = fit_curve(P, closed) if kind == "curve" else fit_circle(P, closed) if kind == "circle" else fit_surface(P, verts, 0)
    for v, p, q in zip(verts, P, Q):
        v.co = p + (q - p) * STRENGTH
    moved += len(verts)
    print(f"  {kind}{' (closed)' if closed else ''}: {len(verts)} verts, max move {np.linalg.norm(Q - P, axis=1).max() * STRENGTH:.4f}")

bmesh.update_edit_mesh(ob.data)
key = ob.active_shape_key.name if ob.active_shape_key else "mesh"
print(f"fit_verts ({MODE}): {moved} verts fitted on '{key}'")
