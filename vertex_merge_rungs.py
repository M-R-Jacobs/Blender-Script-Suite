"""
README:
Merge two rows of verts together, each with the one it's
already connected to (Blender, Edit Mode, run from the Text Editor).

  1. Select both rows, or just the short edges ("rungs") between them 
     (Ctrl+Alt+click one rung = whole ring). Use "center" mode to meet
     in the middle.
  2. To keep ONE row exactly where it is (the other row moves onto it):
     Shift+click a vertex on the row to keep LAST, so it is the active (white)
     vertex, and set KEEP = "active".
  3. Run. Every rung collapses to one vertex; the strip between the rows is gone.

Same as M > Collapse on a ring, plus the option to keep one row in place.
"""
import bpy, bmesh

KEEP = "center"     # "center" = meet in the middle, "active" = keep the active vertex's row

ob = bpy.context.active_object
assert ob and ob.type == 'MESH' and ob.mode == 'EDIT', "Edit Mode, select the rungs"
bm = bmesh.from_edit_mesh(ob.data)
# If whole rows are selected (the strip of quads between them too), find the rungs:
# in a strip of quads, the rungs are the sides shared with the next quad (+ the ends).
strip = [f for f in bm.faces if len(f.verts) == 4 and all(v.select for v in f.verts)]
if strip:
    sset = set(strip); rungs = set()
    for f in strip:
        es = list(f.edges)
        for i, e in enumerate(es):
            if any(g in sset and g is not f for g in e.link_faces):
                rungs.add(e); rungs.add(es[(i + 2) % 4])        # shared side + its opposite
    if not rungs:                                              # a single quad: take the shorter pair
        es = list(strip[0].edges)
        a = (es[0].calc_length() + es[2].calc_length()) < (es[1].calc_length() + es[3].calc_length())
        rungs = {es[0], es[2]} if a else {es[1], es[3]}
    rungs = list(rungs)
else:
    rungs = [e for e in bm.edges if e.select]
assert rungs, "Select both rows (or just the rungs between them)"
rset = set(rungs)

keep_row = set()
if KEEP == "active":
    act = bm.select_history.active
    assert isinstance(act, bmesh.types.BMVert), "Shift+click a vertex on the row to keep (vertex mode) so it is active"
    # the row = verts reachable from the active vertex along non-rung edges between rung ends
    ends = {v for e in rungs for v in e.verts}
    stack = [act]; keep_row.add(act)
    while stack:
        v = stack.pop()
        for e in v.link_edges:
            w = e.other_vert(v)
            if e not in rset and w in ends and w not in keep_row:
                keep_row.add(w); stack.append(w)

n = 0
for e in rungs:
    if not e.is_valid: continue
    a, b = e.verts
    if KEEP == "active" and (a in keep_row) != (b in keep_row):
        k, m = (a, b) if a in keep_row else (b, a)
        bmesh.ops.pointmerge(bm, verts=[k, m], merge_co=k.co.copy())
    else:
        bmesh.ops.pointmerge(bm, verts=[a, b], merge_co=(a.co + b.co) / 2)
    n += 1
bmesh.update_edit_mesh(ob.data)
print(f"merge_rungs: {n} pairs merged ({KEEP})")
