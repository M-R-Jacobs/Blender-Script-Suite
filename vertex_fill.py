"""
README:
connect several verts to ONE vertex, and optionally fill
the wedges between them in Blender's Edit Mode.

Select the verts, then Shift+click the "hub" or apex vertex LAST (it turns white).
Or, in edge mode, just select the spoke edges that meet at one vertex - the
shared vertex is the hub.

MODE:
  "connect"  each selected vert gets an edge to the hub. Where they share a face
             the face is split properly (like J or F); otherwise a plain edge is added.
  "fill"     connect as above, THEN fill each wedge: a spoke, the next spoke and
             the existing edge between their outer ends become ONE face (a
             triangle here). Only neighbours that are already joined by an edge
             get a face - nothing else is bridged.
"""
import bpy, bmesh
from collections import Counter

MODE = "connect"    # "connect" or "fill"

ob = bpy.context.active_object
assert ob and ob.type == 'MESH' and ob.mode == 'EDIT', "Edit Mode, select the verts + the hub last"
bm = bmesh.from_edit_mesh(ob.data)

hub = bm.select_history.active
if not isinstance(hub, bmesh.types.BMVert):          # edge selection: hub = the vertex the spokes share
    sel_e = [e for e in bm.edges if e.select]
    assert sel_e, "Select the verts + the hub last, or the spoke edges"
    hub = Counter(v for e in sel_e for v in e.verts).most_common(1)[0][0]
others = [v for v in bm.verts if v.select and v is not hub]
assert others, "Select the verts to connect, then the hub last"

split = added = 0
for v in others:
    if bm.edges.get((v, hub)): continue
    if set(v.link_faces) & set(hub.link_faces):
        bmesh.ops.connect_verts(bm, verts=[v, hub]); split += 1
    else:
        bm.edges.new((v, hub)); added += 1

filled = []
if MODE == "fill":
    oset = set(others)
    for a in others:
        for e in a.link_edges:
            b = e.other_vert(a)
            if b not in oset or a.index > b.index: continue          # each rim edge once
            if not (bm.edges.get((a, hub)) and bm.edges.get((b, hub))): continue
            if bm.faces.get((hub, a, b)): continue
            # skip if hub, a, b already bound a face together (wedge already filled)
            if set(hub.link_faces) & set(a.link_faces) & set(b.link_faces): continue
            filled.append(bm.faces.new((hub, a, b)))
    if filled:
        bmesh.ops.recalc_face_normals(bm, faces=filled)
        for f in filled: f.select = True

bmesh.update_edit_mesh(ob.data)
print(f"connect several verts to ONE vertex, and optionally fill ({MODE}): {split} faces split, {added} edges added, {len(filled)} wedges filled")
