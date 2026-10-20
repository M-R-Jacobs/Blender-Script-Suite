"""
You modelled on a shape key by accident? Make that
shape the new Basis without losing any other key.

Run in Object Mode (it switches for you), with the mesh you want to operate on active.
  - "That key - Basis" is added to Basis AND to every other key,
    so every other key keeps exactly the motion it had, now on the new shape.
  - The key you modelled on ends up identical to the new Basis (it does
    nothing any more, so ONLY use this if you are okay with a re-sculpt of its 
    own motion afterwards.
  - Mesh coordinates are synced to the new Basis (no stale offsets later).

SAVE A COPY FIRST!
"""
import bpy
import numpy as np

KEY = "jaw width"      # i.e. the key you modelled on (None = the active shape key)

obj = bpy.context.active_object
if obj.mode != 'OBJECT':
    bpy.ops.object.mode_set(mode='OBJECT')
me = obj.data
kbs = me.shape_keys.key_blocks
basis = me.shape_keys.reference_key
K = kbs[KEY] if KEY else obj.active_shape_key
assert K is not None and K != basis, "Pick a key other than Basis"

n = len(me.vertices)
def get(kb):
    a = np.empty(n * 3, dtype=np.float32); kb.data.foreach_get("co", a); return a

D = get(K) - get(basis)                       # the accidental remodel
moved = int((np.linalg.norm(D.reshape(-1, 3), axis=1) > 1e-6).sum())
for kb in kbs:
    if kb != K:
        kb.data.foreach_set("co", get(kb) + D)   # Basis + every other key
me.vertices.foreach_set("co", get(basis))         # sync mesh to new Basis
K.value = 0.0
me.update()
print(f"\nPromoted '{K.name}' to Basis: {moved} verts moved, "
      f"{len(kbs) - 2} other keys carried over. '{K.name}' is now a blank key "
      f"(identical to Basis) - re-sculpt its motion.")