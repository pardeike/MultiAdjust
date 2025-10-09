# Multi Adjust — Blender add-on for fast batch edits

Batch-set transforms for selected objects and set X/Y/Z for selected mesh components with a compact panel and a terse command box.

- **Blender:** 4.2 or newer
- **Panel:** `3D Viewport > N-panel > Multi Adjust`
- **Undo:** supported

## Why
Common edits are repetitive and modal. This add-on sets exact values across many objects or mesh selections in one action.

## Features
**Object Mode**
- Set **Location**, **Rotation**, **Scale**, or **Origin** on all selected objects.
- Location and Origin support **Local** or **World** space write.
- Rotation uses degrees in UI. Works with any rotation mode.
- Batch-toggle viewport or render visibility across the selection.

**Edit Mesh Mode**
- Set **X/Y/Z** for selected vertices, or vertices of selected **edges** or **faces**.
- **Local** or **Global** space write.
- Auto target respects current select mode (vert/edge/face).

**Command Box**
- Fast text input. Mix tokens. Examples:
  `rx=45` · `x=0 z=2` · `scale.y=1.2` · `space=global` · `target=faces`

## Installation
- **Blender Extensions:** search for “Multi Adjust” inside the official extension browser and click *Install*.
- **Manual install:** download the repository as a `.zip`, then use `Edit ▸ Preferences ▸ Add-ons ▸ Install…` and choose the archive.

## Quick start

### 1) Objects
- Select objects.
- In **Multi Adjust > Objects** pick **Location / Rotation / Scale / Origin**.
- Enable axis checkboxes and set values, and optionally toggle **Visibility**.
- Click **Apply to Selected Objects**.

Examples:
- Set all objects' Z rotation to 45 deg: enable **Rotation**, enable **Z**, value `45`, **Apply**.
- Move all objects to world X=1, Z=2: set **Transform: Location**, **Space: World**, enable **X=1** and **Z=2**, **Apply**.
- Re-center origins at world Z=0 without moving geometry: choose **Origin**, **Space: World**, enable **Z=0**, **Apply**.
- Hide the selection in renders but keep it in the viewport: enable **Visibility > Render**, set **Hide**, **Apply**.

### 2) Edit Mesh
- Enter **Edit Mode** on a mesh object.
- Select verts/edges/faces.
- In **Multi Adjust ▸ Edit Mesh**, choose **Affect** (Auto/Verts/Edges/Faces) and **Space** (Local/Global).
- Enable axes and set values.
- Click **Apply to Selected Geometry**.

Example: flatten selected verts to `z=0` in Global space: **Affect: Auto**, **Space: Global**, enable **Z=0**, **Apply**.

### 3) Command box (works in either mode)
Type commands then press **Run**.

- **Bare axes**: `x=0 z=2`
  Object Mode → Location. Edit Mesh → vertex coords.
- **Rotation**: `rx=45`, `rot.z=90`, `ry=1.57rad`
- **Scale**: `sx=2`, `scale.y=1.2`
- **Location**: `loc.x=0 loc.z=2`
- **Origin**: `origin.z=0`, `ox=1` (keeps geometry in place)
- **Space**: `space=local` or `space=global`/`world`
- **Mesh target**: `target=verts|edges|faces|auto`

You can combine:
`rx=45 space=world` (Object Mode)
`x=0 z=2 space=global target=faces` (Edit Mesh)

Note: if a single command includes multiple object transforms, priority is **Rotation > Scale > Origin > Location**.

## Reference

### Tokens
| Token            | Meaning                                  |
|------------------|-------------------------------------------|
| `x=. y=. z=.`    | Set axes (Object Mode: Location; Edit: coords) |
| `rx=. ry=. rz=.` | Rotation in degrees by default; add `rad` |
| `sx=. sy=. sz=.` | Scale                                     |
| `loc.x=.`        | Object Location component                 |
| `origin.z=.` or `oz=.` | Object Origin component (keeps geometry in place) |
| `rot.y=.`        | Object Rotation component                 |
| `scale.z=.` or `s.z=.` | Object Scale component             |
| `space=local|global|world` | Write space                     |
| `target=verts|edges|faces|auto` | Mesh elements to affect    |
### Units
- Rotation: degrees by default; append `rad` for radians.
- Distances: scene units.

### Selection resolution in Edit Mesh
- **Auto** uses the current select mode.
  Vert mode → selected verts.
  Edge mode → verts of selected edges.
  Face mode → verts of selected faces.

## Tips
- Use the **Origin** transform to reposition pivots while keeping geometry where it is.
- World-space writes are supported for **Location** in Object Mode and for mesh coordinates in **Global** space. Rotation and Scale apply in local space.
- Works with any object type that has location/rotation/scale.
- All operations are undoable.

## Troubleshooting
- **"No selected objects"**: select at least one editable object in Object Mode.
- **"Need a mesh in Edit Mode"**: enter Edit Mode on a mesh.
- **"No verts resolved from selection"**: adjust selection or set **Affect**.
- **"No axis enabled"**: toggle the X/Y/Z checkboxes or supply axis tokens in the command.

## Limitations
- Object **Rotation** and **Scale** write in local space only.
- Mesh editing affects the **active mesh object** in Edit Mode. Multi-object Edit Mode is not supported by this operator.
- The command box applies one object transform category per run (see priority rule).

The add-on targets Blender 4.2+ and is released under the GPLv3 license.

## Feedback & Contributions
Bug reports, ideas, and pull requests are welcome. Open an issue on the GitHub repository or reach out to the maintainer listed in the manifest. Happy blending!