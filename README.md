# Multi Adjust

<img alt="MultiAdjustScreenshot" src="https://github.com/user-attachments/assets/cc8fca66-a5e3-455a-8852-440cde0db43c" />

Multi Adjust keeps common Blender tweaks in one place so you can nudge several things at once instead of repeating the same move.

## What you can do
- Match location, rotation, scale, or origin for every selected object with one click.
- Swap between local and world space when aligning objects or mesh points.
- Flatten or align mesh selections and curve handles by typing the X, Y, or Z value you want.
- Tweak curve weight, radius, or tilt while you adjust their position.
- Flip viewport or render visibility for the whole selection in a single pass.

## Using the panel
1. Select a few objects, mesh elements, or curve points.
2. Open the **Multi Adjust** tab in the 3D Viewport sidebar.
3. Turn on the axes you care about and type the numbers.
4. Press the apply button that matches your current mode.

## Command box
Prefer typing? Pop a short line like `rx=45`, `x=0 z=2`, or `target=faces space=global` into the command box and hit **Run**. Multi Adjust reads the words, updates the panel, and runs the right action right away.

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
| `space=local / global / world` | Write space                     |
| `target=verts / edges / faces / auto` | Mesh elements to affect    |
### Units
- Rotation: degrees by default; append `rad` for radians.
- Distances: scene units.

## Friendly notes
- Everything respects Blender's undo history.
- Built for Blender 4.2 and newer.
- If nothing changes, make sure an axis is enabled or the command includes a value.
- Feedback and ideas are welcome; check the add-on manifest for contact details.
