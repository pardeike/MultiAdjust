# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2025 Andreas Pardeike

# pyright: reportInvalidTypeForm=false

from .manifest import parse_manifest
bl_info = parse_manifest({"location": "3D Viewport > N-panel > Multi Adjust", "category": "3D View"})

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
            ('ORIGIN', "Origin", "Set object origin without moving geometry"),
        ],
        default='ROT'
    )

    object_space: bpy.props.EnumProperty(
        name="Space",
        description="Space for object Location or Origin setting",
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

    # Curve attributes (Edit Curve mode)
    curve_weight_enable: bpy.props.BoolProperty(name="Weight", default=False)
    curve_weight_value: bpy.props.FloatProperty(name="Weight", default=1.0)
    curve_radius_enable: bpy.props.BoolProperty(name="Radius", default=False)
    curve_radius_value: bpy.props.FloatProperty(name="Radius", default=1.0)
    curve_tilt_enable: bpy.props.BoolProperty(name="Tilt", default=False)
    curve_tilt_value: bpy.props.FloatProperty(name="Tilt", default=0.0)

    # Command line
    command: bpy.props.StringProperty(
        name="Command",
        description="e.g. rx=45  x=0 z=2  space=global  target=faces  scale.y=1.2",
        default=""
    )

    # Visibility batch toggles
    vis_apply_viewport: bpy.props.BoolProperty(
        name="Viewport",
        description="Apply viewport visibility to selected objects",
        default=False
    )
    vis_viewport_hide: bpy.props.BoolProperty(
        name="Hide in Viewport",
        description="Hide selected objects in the viewport (requires Viewport toggle)",
        default=False
    )
    vis_apply_render: bpy.props.BoolProperty(
        name="Render",
        description="Apply render visibility to selected objects",
        default=False
    )
    vis_render_hide: bpy.props.BoolProperty(
        name="Hide in Render",
        description="Hide selected objects from rendering (requires Render toggle)",
        default=False
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

def _set_object_origin(obj: bpy.types.Object, x=None, y=None, z=None, space='LOCAL'):
    """
    Move the object's origin without moving its visible geometry.
    Values are interpreted in either local or world space depending on `space`.
    """
    mw_before = obj.matrix_world.copy()
    translation_before = mw_before.translation.copy()

    if space == 'WORLD':
        target_translation = translation_before.copy()
        if x is not None: target_translation.x = x
        if y is not None: target_translation.y = y
        if z is not None: target_translation.z = z
        if (target_translation - translation_before).length_squared != 0.0:
            mw_new = mw_before.copy()
            mw_new.translation = target_translation
            obj.matrix_world = mw_new
    else:
        target_location = obj.location.copy()
        if x is not None: target_location.x = x
        if y is not None: target_location.y = y
        if z is not None: target_location.z = z
        if target_location != obj.location:
            obj.location = target_location

    translation_after = obj.matrix_world.translation.copy()
    delta_world = translation_after - translation_before
    if delta_world.length_squared == 0.0:
        return

    data = getattr(obj, "data", None)
    if not data or not hasattr(data, "transform"):
        # Nothing to offset (empties, cameras, etc.)
        return

    # Ensure we do not affect other objects sharing the same datablock
    if getattr(data, "users", 1) > 1:
        data = data.copy()
        obj.data = data

    orient = mw_before.to_3x3()
    try:
        orient_inv = orient.inverted()
    except (ValueError, ZeroDivisionError):
        return
    delta_local = orient_inv @ delta_world

    data.transform(Matrix.Translation(-delta_local))
    updater = getattr(data, "update", None)
    if callable(updater):
        try:
            updater()
        except TypeError:
            # Some datablocks expect keyword arguments; best effort with defaults
            try:
                updater(calc_edges=False)
            except TypeError:
                pass

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
        elif P.apply_transform == 'ORIGIN':
            for obj in objs:
                _set_object_origin(obj, X, Y, Z, P.object_space)

        if P.vis_apply_viewport:
            for obj in objs:
                obj.hide_set(P.vis_viewport_hide)
        if P.vis_apply_render:
            for obj in objs:
                obj.hide_render = P.vis_render_hide

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

class QS_OT_apply_curve(bpy.types.Operator):
    bl_idname = "view3d.qs_apply_curve"
    bl_label = "Apply to Curve"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'CURVE' or context.mode != 'EDIT_CURVE':
            self.report({'INFO'}, "Need a curve in Edit Mode")
            return {'CANCELLED'}

        scn = context.scene
        P = scn.qs

        X = P.x_value if P.x_enable else None
        Y = P.y_value if P.y_enable else None
        Z = P.z_value if P.z_enable else None
        weight_val = P.curve_weight_value if P.curve_weight_enable else None
        radius_val = P.curve_radius_value if P.curve_radius_enable else None
        tilt_val = P.curve_tilt_value if P.curve_tilt_enable else None

        position_enabled = any(v is not None for v in (X, Y, Z))
        attributes_enabled = any(v is not None for v in (weight_val, radius_val, tilt_val))
        if not position_enabled and not attributes_enabled:
            self.report({'INFO'}, "No values enabled")
            return {'CANCELLED'}

        crv = obj.data
        mw = obj.matrix_world.copy()
        use_global = (P.mesh_space == 'GLOBAL')
        if use_global:
            try:
                imw = mw.inverted()
            except (ValueError, ZeroDivisionError):
                imw = None
                use_global = False
        else:
            imw = None

        def transform_vector(local_vec: Vector) -> Vector:
            if not position_enabled:
                return local_vec
            if use_global and imw is not None:
                world_vec = mw @ local_vec
                if X is not None: world_vec.x = X
                if Y is not None: world_vec.y = Y
                if Z is not None: world_vec.z = Z
                return imw @ world_vec
            new_vec = local_vec.copy()
            if X is not None: new_vec.x = X
            if Y is not None: new_vec.y = Y
            if Z is not None: new_vec.z = Z
            return new_vec

        any_selected = False
        position_applied = False
        attr_requested = {
            'weight': weight_val is not None,
            'radius': radius_val is not None,
            'tilt': tilt_val is not None,
        }
        attr_applied = {'weight': False, 'radius': False, 'tilt': False}
        unsupported_weight = False

        for spline in crv.splines:
            if spline.type == 'BEZIER':
                for bp in spline.bezier_points:
                    if bp.select_control_point:
                        any_selected = True
                        if position_enabled:
                            new_local = transform_vector(bp.co.copy())
                            bp.co = new_local
                            position_applied = True
                        if attributes_enabled:
                            if weight_val is not None:
                                if hasattr(bp, "weight"):
                                    bp.weight = weight_val
                                    attr_applied['weight'] = True
                                else:
                                    unsupported_weight = True
                            if radius_val is not None:
                                bp.radius = radius_val
                                attr_applied['radius'] = True
                            if tilt_val is not None:
                                bp.tilt = tilt_val
                                attr_applied['tilt'] = True
                    if position_enabled and bp.select_left_handle:
                        any_selected = True
                        bp.handle_left = transform_vector(bp.handle_left.copy())
                        position_applied = True
                    if position_enabled and bp.select_right_handle:
                        any_selected = True
                        bp.handle_right = transform_vector(bp.handle_right.copy())
                        position_applied = True
            else:
                for pt in spline.points:
                    if not pt.select:
                        continue
                    any_selected = True
                    if position_enabled:
                        co4 = pt.co
                        local = Vector((co4[0], co4[1], co4[2]))
                        new_local = transform_vector(local)
                        pt.co = (new_local.x, new_local.y, new_local.z, co4[3])
                        position_applied = True
                    if attributes_enabled:
                        if weight_val is not None:
                            pt.weight = weight_val
                            attr_applied['weight'] = True
                        if radius_val is not None:
                            pt.radius = radius_val
                            attr_applied['radius'] = True
                        if tilt_val is not None:
                            pt.tilt = tilt_val
                            attr_applied['tilt'] = True

        if not any_selected:
            self.report({'INFO'}, "No selected curve points or handles")
            return {'CANCELLED'}
        if position_enabled and not position_applied:
            self.report({'INFO'}, "No selected elements for position")
            return {'CANCELLED'}
        if attributes_enabled:
            if not any(attr_applied.values()):
                if attr_requested['weight'] and unsupported_weight and not (attr_requested['radius'] or attr_requested['tilt']):
                    self.report({'INFO'}, "Weight not supported for selected curve points")
                else:
                    self.report({'INFO'}, "No control points for attributes")
                return {'CANCELLED'}
            if attr_requested['weight'] and not attr_applied['weight'] and unsupported_weight:
                self.report({'WARNING'}, "Weight not supported for selected curve points")

        updater = getattr(crv, "update", None)
        if callable(updater):
            try:
                updater()
            except TypeError:
                try:
                    updater(calc_edges=False)
                except TypeError:
                    pass
        crv.update_tag()
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
        target_curve = (context.mode == 'EDIT_CURVE')
        pending_object_loc = False
        pending_object_origin = False

        # Local state for parsed values
        obj_loc = {'x': None, 'y': None, 'z': None}
        obj_rot = {'x': None, 'y': None, 'z': None}  # degrees
        obj_sca = {'x': None, 'y': None, 'z': None}
        obj_origin = {'x': None, 'y': None, 'z': None}
        mesh_xyz = {'x': None, 'y': None, 'z': None}
        obj_space_world = None
        mesh_space_global = None
        curve_space_global = None
        mesh_target = None
        curve_attrs = {'weight': None, 'radius': None, 'tilt': None}

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
                    elif target_curve:
                        curve_space_global = True
                    else:
                        obj_space_world = True
                elif vv in ('local',):
                    if target_mesh:
                        mesh_space_global = False
                    elif target_curve:
                        curve_space_global = False
                    else:
                        obj_space_world = False
                continue
            if k == 'target':
                vv = v.lower()
                if vv in ('verts', 'vert', 'v'):
                    mesh_target = 'VERT'
                    target_mesh = True
                    target_curve = False
                elif vv in ('edges', 'edge', 'e'):
                    mesh_target = 'EDGE'
                    target_mesh = True
                    target_curve = False
                elif vv in ('faces', 'face', 'f'):
                    mesh_target = 'FACE'
                    target_mesh = True
                    target_curve = False
                elif vv in ('auto',):
                    mesh_target = 'AUTO'
                    target_mesh = True
                    target_curve = False
                continue

            # loc.x / rot.y / scale.z
            if k.startswith('loc.'):
                axis = k[-1]
                valf, _ = _parse_float_with_unit(v)
                assign_map(obj_loc, axis, valf)
                pending_object_loc = True
                target_mesh = False
                target_curve = False
                continue
            if k.startswith('rot.'):
                axis = k[-1]
                valf, unit = _parse_float_with_unit(v)
                if unit == 'rad':
                    valf = valf * 180.0 / 3.141592653589793
                assign_map(obj_rot, axis, valf)
                target_mesh = False
                target_curve = False
                continue
            if k.startswith('scale.') or k.startswith('s.'):
                axis = k[-1]
                valf, _ = _parse_float_with_unit(v)
                assign_map(obj_sca, axis, valf)
                target_mesh = False
                target_curve = False
                continue
            if k.startswith('origin.') or k.startswith('orig.') or k.startswith('o.'):
                axis = k[-1]
                valf, _ = _parse_float_with_unit(v)
                assign_map(obj_origin, axis, valf)
                pending_object_origin = True
                target_mesh = False
                target_curve = False
                continue

            # Shorthand: rx, ry, rz (deg by default)
            if k in ('rx', 'ry', 'rz'):
                axis = k[-1]
                valf, unit = _parse_float_with_unit(v)
                if unit == 'rad':
                    valf = valf * 180.0 / 3.141592653589793
                assign_map(obj_rot, axis, valf)
                target_mesh = False
                target_curve = False
                continue
            # Shorthand: sx, sy, sz
            if k in ('sx', 'sy', 'sz'):
                axis = k[-1]
                valf, _ = _parse_float_with_unit(v)
                assign_map(obj_sca, axis, valf)
                target_mesh = False
                target_curve = False
                continue
            if k in ('ox', 'oy', 'oz'):
                axis = k[-1]
                valf, _ = _parse_float_with_unit(v)
                assign_map(obj_origin, axis, valf)
                pending_object_origin = True
                target_mesh = False
                target_curve = False
                continue

            # Bare x,y,z -> mesh if in Edit Mesh, else object Location
            if k in ('x', 'y', 'z'):
                valf, _ = _parse_float_with_unit(v)
                if context.mode == 'EDIT_MESH':
                    mesh_xyz[k] = valf
                    target_mesh = True
                    target_curve = False
                elif context.mode == 'EDIT_CURVE':
                    mesh_xyz[k] = valf
                    target_curve = True
                    target_mesh = False
                else:
                    obj_loc[k] = valf
                    pending_object_loc = True
                    target_mesh = False
                    target_curve = False
                continue
            if k in ('weight', 'radius', 'tilt'):
                valf, _ = _parse_float_with_unit(v)
                curve_attrs[k] = valf
                target_curve = True
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
        if target_curve:
            if curve_space_global is not None:
                P.mesh_space = 'GLOBAL' if curve_space_global else 'LOCAL'

            P.x_enable = mesh_xyz['x'] is not None
            P.y_enable = mesh_xyz['y'] is not None
            P.z_enable = mesh_xyz['z'] is not None
            if P.x_enable: P.x_value = mesh_xyz['x']
            if P.y_enable: P.y_value = mesh_xyz['y']
            if P.z_enable: P.z_value = mesh_xyz['z']

            P.curve_weight_enable = curve_attrs['weight'] is not None
            P.curve_radius_enable = curve_attrs['radius'] is not None
            P.curve_tilt_enable = curve_attrs['tilt'] is not None
            if P.curve_weight_enable: P.curve_weight_value = curve_attrs['weight']
            if P.curve_radius_enable: P.curve_radius_value = curve_attrs['radius']
            if P.curve_tilt_enable: P.curve_tilt_value = curve_attrs['tilt']

            return bpy.ops.view3d.qs_apply_curve()

        # Object path
        if obj_space_world is not None:
            P.object_space = 'WORLD' if obj_space_world else 'LOCAL'

        # Decide transform priority: rotation > scale > origin > location
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
        elif pending_object_origin or any(v is not None for v in obj_origin.values()):
            P.apply_transform = 'ORIGIN'
            P.x_enable = obj_origin['x'] is not None
            P.y_enable = obj_origin['y'] is not None
            P.z_enable = obj_origin['z'] is not None
            if P.x_enable: P.x_value = obj_origin['x']
            if P.y_enable: P.y_value = obj_origin['y']
            if P.z_enable: P.z_value = obj_origin['z']
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

class VIEW3D_PT_multi_adjust(bpy.types.Panel):
    bl_label = "Multi Adjust"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Multi Adjust"

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
            if P.apply_transform in {'LOC', 'ORIGIN'}:
                row = box.row(align=True)
                row.prop(P, "object_space", expand=True)

            col = box.column(align=True)
            r = col.row(align=True)
            r.prop(P, "x_enable"); r.prop(P, "x_value")
            r = col.row(align=True)
            r.prop(P, "y_enable"); r.prop(P, "y_value")
            r = col.row(align=True)
            r.prop(P, "z_enable"); r.prop(P, "z_value")

            box.separator()
            box.label(text="Visibility")
            row = box.row(align=True)
            row.prop(P, "vis_apply_viewport", text="Viewport", toggle=True)
            sub = row.row(align=True)
            sub.enabled = P.vis_apply_viewport
            sub.prop(P, "vis_viewport_hide", text="Hide", toggle=True)
            row = box.row(align=True)
            row.prop(P, "vis_apply_render", text="Render", toggle=True)
            sub = row.row(align=True)
            sub.enabled = P.vis_apply_render
            sub.prop(P, "vis_render_hide", text="Hide", toggle=True)

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
        elif context.mode == 'EDIT_CURVE':
            box = layout.box()
            box.label(text="Edit Curve")
            row = box.row(align=True)
            row.prop(P, "mesh_space", expand=True)

            col = box.column(align=True)
            r = col.row(align=True)
            r.prop(P, "x_enable"); r.prop(P, "x_value")
            r = col.row(align=True)
            r.prop(P, "y_enable"); r.prop(P, "y_value")
            r = col.row(align=True)
            r.prop(P, "z_enable"); r.prop(P, "z_value")

            box.separator()
            box.label(text="Attributes")
            col = box.column(align=True)
            r = col.row(align=True)
            r.prop(P, "curve_weight_enable"); r.prop(P, "curve_weight_value")
            r = col.row(align=True)
            r.prop(P, "curve_radius_enable"); r.prop(P, "curve_radius_value")
            r = col.row(align=True)
            r.prop(P, "curve_tilt_enable"); r.prop(P, "curve_tilt_value")

            box.operator(QS_OT_apply_curve.bl_idname, text="Apply to Selected Points")
        else:
            layout.label(text="Switch to Object or Edit Mesh for controls")

# ------------------------- Registration -------------------------

classes = (
    QS_Props,
    QS_OT_apply_object,
    QS_OT_apply_mesh,
    QS_OT_apply_curve,
    QS_OT_parse_and_apply,
    VIEW3D_PT_multi_adjust,
)

def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.qs = bpy.props.PointerProperty(type=QS_Props)
    print("Registered MultiAdjust")

def unregister():
    del bpy.types.Scene.qs
    for c in reversed(classes):
        bpy.utils.unregister_class(c)

if __name__ == "__main__":
    register()
