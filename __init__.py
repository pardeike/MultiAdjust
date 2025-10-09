# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2025 Andreas Pardeike

# pyright: reportInvalidTypeForm=false

from .manifest import parse_manifest
bl_info = parse_manifest({"location": "3D Viewport > N-panel > Quick Set", "category": "3D View"})

import re
import bpy
import bmesh
from math import radians
from mathutils import Matrix, Vector, Euler

# ------------------------- Properties -------------------------

class QS_Props(bpy.types.PropertyGroup):
    # Mode-aware toggles and values
    apply_transform: bpy.props.EnumProperty(
        name="Transform",
        items=[
            ('LOC', "Location", "Set object location"),
            ('ROT', "Rotation", "Set object rotation (Euler)"),
            ('SCALE', "Scale", "Set object scale"),
        ],
        default='ROT'
    )

    object_space: bpy.props.EnumProperty(
        name="Space",
        description="Space for object Location setting",
        items=[('LOCAL', "Local", ""), ('WORLD', "World", "")],
        default='LOCAL'
    )

    mesh_space: bpy.props.EnumProperty(
        name="Space",
        items=[('LOCAL', "Local", ""), ('GLOBAL', "Global", "")],
        default='LOCAL'
    )

    mesh_target: bpy.props.EnumProperty(
        name="Affect",
        items=[
            ('AUTO', "Auto", "Use current mesh select mode"),
            ('VERT', "Verts", "Selected vertices"),
            ('EDGE', "Edges", "Vertices of selected edges"),
            ('FACE', "Faces", "Vertices of selected faces"),
        ],
        default='AUTO'
    )

    # Axis enables
    x_enable: bpy.props.BoolProperty(name="X", default=False)
    y_enable: bpy.props.BoolProperty(name="Y", default=False)
    z_enable: bpy.props.BoolProperty(name="Z", default=False)

    # Axis values (object: deg for rotation; mesh: units)
    x_value: bpy.props.FloatProperty(name="X", default=0.0)
    y_value: bpy.props.FloatProperty(name="Y", default=0.0)
    z_value: bpy.props.FloatProperty(name="Z", default=0.0)

    # Command line
    command: bpy.props.StringProperty(
        name="Command",
        description="e.g. rx=45  x=0 z=2  space=global  target=faces  scale.y=1.2",
        default=""
    )

# ------------------------- Utilities -------------------------

def _set_world_translation(obj: bpy.types.Object, x=None, y=None, z=None):
    mw = obj.matrix_world.copy()
    t = mw.translation.copy()
    if x is not None: t.x = x
    if y is not None: t.y = y
    if z is not None: t.z = z
    mw.translation = t
    obj.matrix_world = mw  # lets Blender solve local transforms

def _get_euler_from_object(obj: bpy.types.Object) -> Euler:
    mode = obj.rotation_mode
    if mode == 'QUATERNION':
        e = obj.rotation_quaternion.to_euler('XYZ')
    elif mode == 'AXIS_ANGLE':
        ang = obj.rotation_axis_angle[0]
        axis = Vector(obj.rotation_axis_angle[1:4])
        mat = Matrix.Rotation(ang, 4, axis)
        e = mat.to_euler('XYZ')
    else:
        e = obj.rotation_euler.copy()
        e.order = mode
    return e

def _apply_euler_to_object(obj: bpy.types.Object, e: Euler):
    mode = obj.rotation_mode
    if mode == 'QUATERNION':
        obj.rotation_quaternion = e.to_quaternion()
    elif mode == 'AXIS_ANGLE':
        axis, ang = e.to_quaternion().to_axis_angle()
        obj.rotation_axis_angle[0] = ang
        obj.rotation_axis_angle[1] = axis.x
        obj.rotation_axis_angle[2] = axis.y
        obj.rotation_axis_angle[3] = axis.z
    else:
        e2 = Euler((e.x, e.y, e.z), mode)
        obj.rotation_euler = e2

def _selected_bm_verts(bm, target: str, context) -> set:
    vmode, emode, fmode = context.tool_settings.mesh_select_mode
    verts = set()
    if target == 'AUTO':
        if vmode:
            for v in bm.verts:
                if v.select: verts.add(v)
        elif emode:
            for e in bm.edges:
                if e.select:
                    verts.update(e.verts)
        elif fmode:
            for f in bm.faces:
                if f.select:
                    verts.update(f.verts)
    elif target == 'VERT':
        for v in bm.verts:
            if v.select: verts.add(v)
    elif target == 'EDGE':
        for e in bm.edges:
            if e.select:
                verts.update(e.verts)
    elif target == 'FACE':
        for f in bm.faces:
            if f.select:
                verts.update(f.verts)
    return verts

def _parse_float_with_unit(s: str):
    """
    Accepts e.g. '45', '45d', '45deg', '0.785r', '0.785rad'
    Returns (value, unit) where unit in {'deg','rad',None}
    """
    s = s.strip().lower()
    m = re.fullmatch(r'([+-]?\d*\.?\d+(?:[eE][+-]?\d+)?)([a-z]*)', s)
    if not m:
        return None, None
    val = float(m.group(1))
    unit = m.group(2)
    if unit in ("d", "deg"):
        return val, "deg"
    if unit in ("r", "rad"):
        return val, "rad"
    return val, None

# ------------------------- Operators -------------------------

class QS_OT_apply_object(bpy.types.Operator):
    bl_idname = "view3d.qs_apply_object"
    bl_label = "Apply to Objects"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scn = context.scene
        P = scn.qs

        objs = [o for o in context.selected_editable_objects]
        if not objs:
            self.report({'INFO'}, "No selected objects")
            return {'CANCELLED'}

        X = P.x_value if P.x_enable else None
        Y = P.y_value if P.y_enable else None
        Z = P.z_value if P.z_enable else None

        if P.apply_transform == 'LOC':
            for obj in objs:
                if P.object_space == 'WORLD':
                    _set_world_translation(obj, X, Y, Z)
                else:
                    if X is not None: obj.location.x = X
                    if Y is not None: obj.location.y = Y
                    if Z is not None: obj.location.z = Z

        elif P.apply_transform == 'ROT':
            # Inputs interpreted as degrees
            rx = radians(P.x_value) if P.x_enable else None
            ry = radians(P.y_value) if P.y_enable else None
            rz = radians(P.z_value) if P.z_enable else None

            for obj in objs:
                e = _get_euler_from_object(obj)
                if rx is not None: e.x = rx
                if ry is not None: e.y = ry
                if rz is not None: e.z = rz
                _apply_euler_to_object(obj, e)

        elif P.apply_transform == 'SCALE':
            for obj in objs:
                if X is not None: obj.scale.x = X
                if Y is not None: obj.scale.y = Y
                if Z is not None: obj.scale.z = Z

        return {'FINISHED'}

class QS_OT_apply_mesh(bpy.types.Operator):
    bl_idname = "view3d.qs_apply_mesh"
    bl_label = "Apply to Mesh"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH' or context.mode != 'EDIT_MESH':
            self.report({'INFO'}, "Need a mesh in Edit Mode")
            return {'CANCELLED'}

        scn = context.scene
        P = scn.qs

        X = P.x_value if P.x_enable else None
        Y = P.y_value if P.y_enable else None
        Z = P.z_value if P.z_enable else None
        if X is None and Y is None and Z is None:
            self.report({'INFO'}, "No axis enabled")
            return {'CANCELLED'}

        me = obj.data
        bm = bmesh.from_edit_mesh(me)

        verts = _selected_bm_verts(bm, P.mesh_target, context)
        if not verts:
            self.report({'INFO'}, "No verts resolved from selection")
            return {'CANCELLED'}

        mw = obj.matrix_world
        imw = mw.inverted()

        if P.mesh_space == 'GLOBAL':
            for v in verts:
                w = mw @ v.co
                if X is not None: w.x = X
                if Y is not None: w.y = Y
                if Z is not None: w.z = Z
                v.co = imw @ w
        else:
            for v in verts:
                if X is not None: v.co.x = X
                if Y is not None: v.co.y = Y
                if Z is not None: v.co.z = Z

        bmesh.update_edit_mesh(me, loop_triangles=False, destructive=False)
        return {'FINISHED'}

class QS_OT_parse_and_apply(bpy.types.Operator):
    bl_idname = "view3d.qs_parse_and_apply"
    bl_label = "Run Command"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scn = context.scene
        P = scn.qs
        line = (P.command or "").strip()
        if not line:
            self.report({'INFO'}, "Empty command")
            return {'CANCELLED'}

        # Reset enables
        P.x_enable = P.y_enable = P.z_enable = False

        tokens = [t for t in re.split(r'[\s,]+', line) if t]
        # Heuristics: default target by context
        target_mesh = (context.mode == 'EDIT_MESH')
        pending_object_loc = False

        # Local state for parsed values
        obj_loc = {'x': None, 'y': None, 'z': None}
        obj_rot = {'x': None, 'y': None, 'z': None}  # degrees
        obj_sca = {'x': None, 'y': None, 'z': None}
        mesh_xyz = {'x': None, 'y': None, 'z': None}
        obj_space_world = None
        mesh_space_global = None
        mesh_target = None

        # Maps like loc.x, rot.y, scale.z
        def assign_map(mapref, axis, val):
            if axis in ('x', 'y', 'z'):
                mapref[axis] = val

        for t in tokens:
            if '=' not in t:
                continue
            key, val = t.split('=', 1)
            k = key.strip().lower()
            v = val.strip()

            # Space and target
            if k == 'space':
                vv = v.lower()
                if vv in ('global', 'world'):
                    if target_mesh:
                        mesh_space_global = True
                    else:
                        obj_space_world = True
                elif vv in ('local',):
                    if target_mesh:
                        mesh_space_global = False
                    else:
                        obj_space_world = False
                continue
            if k == 'target':
                vv = v.lower()
                if vv in ('verts', 'vert', 'v'):
                    mesh_target = 'VERT'
                    target_mesh = True
                elif vv in ('edges', 'edge', 'e'):
                    mesh_target = 'EDGE'
                    target_mesh = True
                elif vv in ('faces', 'face', 'f'):
                    mesh_target = 'FACE'
                    target_mesh = True
                elif vv in ('auto',):
                    mesh_target = 'AUTO'
                    target_mesh = True
                continue

            # loc.x / rot.y / scale.z
            if k.startswith('loc.'):
                axis = k[-1]
                valf, _ = _parse_float_with_unit(v)
                assign_map(obj_loc, axis, valf)
                pending_object_loc = True
                target_mesh = False
                continue
            if k.startswith('rot.'):
                axis = k[-1]
                valf, unit = _parse_float_with_unit(v)
                if unit == 'rad':
                    valf = valf * 180.0 / 3.141592653589793
                assign_map(obj_rot, axis, valf)
                target_mesh = False
                continue
            if k.startswith('scale.') or k.startswith('s.'):
                axis = k[-1]
                valf, _ = _parse_float_with_unit(v)
                assign_map(obj_sca, axis, valf)
                target_mesh = False
                continue

            # Shorthand: rx, ry, rz (deg by default)
            if k in ('rx', 'ry', 'rz'):
                axis = k[-1]
                valf, unit = _parse_float_with_unit(v)
                if unit == 'rad':
                    valf = valf * 180.0 / 3.141592653589793
                assign_map(obj_rot, axis, valf)
                target_mesh = False
                continue
            # Shorthand: sx, sy, sz
            if k in ('sx', 'sy', 'sz'):
                axis = k[-1]
                valf, _ = _parse_float_with_unit(v)
                assign_map(obj_sca, axis, valf)
                target_mesh = False
                continue

            # Bare x,y,z -> mesh if in Edit Mesh, else object Location
            if k in ('x', 'y', 'z'):
                valf, _ = _parse_float_with_unit(v)
                if context.mode == 'EDIT_MESH':
                    mesh_xyz[k] = valf
                    target_mesh = True
                else:
                    obj_loc[k] = valf
                    pending_object_loc = True
                    target_mesh = False
                continue

        # Push into UI props and execute appropriate operator
        if target_mesh:
            # Mesh path
            if mesh_space_global is not None:
                P.mesh_space = 'GLOBAL' if mesh_space_global else 'LOCAL'
            if mesh_target is not None:
                P.mesh_target = mesh_target

            # Axis enables
            P.x_enable = mesh_xyz['x'] is not None
            P.y_enable = mesh_xyz['y'] is not None
            P.z_enable = mesh_xyz['z'] is not None
            if P.x_enable: P.x_value = mesh_xyz['x']
            if P.y_enable: P.y_value = mesh_xyz['y']
            if P.z_enable: P.z_value = mesh_xyz['z']
            return bpy.ops.view3d.qs_apply_mesh()

        # Object path
        if obj_space_world is not None:
            P.object_space = 'WORLD' if obj_space_world else 'LOCAL'

        # Decide transform priority: rotation > scale > location
        if any(v is not None for v in obj_rot.values()):
            P.apply_transform = 'ROT'
            P.x_enable = obj_rot['x'] is not None
            P.y_enable = obj_rot['y'] is not None
            P.z_enable = obj_rot['z'] is not None
            if P.x_enable: P.x_value = obj_rot['x']
            if P.y_enable: P.y_value = obj_rot['y']
            if P.z_enable: P.z_value = obj_rot['z']
        elif any(v is not None for v in obj_sca.values()):
            P.apply_transform = 'SCALE'
            P.x_enable = obj_sca['x'] is not None
            P.y_enable = obj_sca['y'] is not None
            P.z_enable = obj_sca['z'] is not None
            if P.x_enable: P.x_value = obj_sca['x']
            if P.y_enable: P.y_value = obj_sca['y']
            if P.z_enable: P.z_value = obj_sca['z']
        elif pending_object_loc or any(v is not None for v in obj_loc.values()):
            P.apply_transform = 'LOC'
            P.x_enable = obj_loc['x'] is not None
            P.y_enable = obj_loc['y'] is not None
            P.z_enable = obj_loc['z'] is not None
            if P.x_enable: P.x_value = obj_loc['x']
            if P.y_enable: P.y_value = obj_loc['y']
            if P.z_enable: P.z_value = obj_loc['z']
        else:
            self.report({'INFO'}, "Nothing to apply")
            return {'CANCELLED'}

        return bpy.ops.view3d.qs_apply_object()

# ------------------------- UI Panel -------------------------

class VIEW3D_PT_quick_set(bpy.types.Panel):
    bl_label = "Quick Set"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Quick Set"

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        layout = self.layout
        scn = context.scene
        P = scn.qs

        # Command box
        box = layout.box()
        box.label(text="Command")
        row = box.row(align=True)
        row.prop(P, "command", text="")
        row.operator(QS_OT_parse_and_apply.bl_idname, text="Run")

        # Mode-specific structured UI
        if context.mode == 'OBJECT':
            box = layout.box()
            box.label(text="Objects")
            row = box.row(align=True)
            row.prop(P, "apply_transform", expand=True)
            if P.apply_transform == 'LOC':
                row = box.row(align=True)
                row.prop(P, "object_space", expand=True)

            col = box.column(align=True)
            r = col.row(align=True)
            r.prop(P, "x_enable"); r.prop(P, "x_value")
            r = col.row(align=True)
            r.prop(P, "y_enable"); r.prop(P, "y_value")
            r = col.row(align=True)
            r.prop(P, "z_enable"); r.prop(P, "z_value")

            box.operator(QS_OT_apply_object.bl_idname, text="Apply to Selected Objects")

        elif context.mode == 'EDIT_MESH':
            box = layout.box()
            box.label(text="Edit Mesh")
            row = box.row(align=True)
            row.prop(P, "mesh_target", expand=True)
            row = box.row(align=True)
            row.prop(P, "mesh_space", expand=True)

            col = box.column(align=True)
            r = col.row(align=True)
            r.prop(P, "x_enable"); r.prop(P, "x_value")
            r = col.row(align=True)
            r.prop(P, "y_enable"); r.prop(P, "y_value")
            r = col.row(align=True)
            r.prop(P, "z_enable"); r.prop(P, "z_value")

            box.operator(QS_OT_apply_mesh.bl_idname, text="Apply to Selected Geometry")
        else:
            layout.label(text="Switch to Object or Edit Mesh for controls")

# ------------------------- Registration -------------------------

classes = (
    QS_Props,
    QS_OT_apply_object,
    QS_OT_apply_mesh,
    QS_OT_parse_and_apply,
    VIEW3D_PT_quick_set,
)

def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.qs = bpy.props.PointerProperty(type=QS_Props)

def unregister():
    del bpy.types.Scene.qs
    for c in reversed(classes):
        bpy.utils.unregister_class(c)

if __name__ == "__main__":
    register()