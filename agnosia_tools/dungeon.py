import bpy
import mathutils

from bpy.types import Object, Operator, PropertyGroup
from mathutils import Vector

class ToolsOperator(Operator):
    bl_idname = "agnosia.dungeon_tools"
    bl_label = "Dungeon Tools"
    # bl_options = {'REGISTER', 'UNDO'}

    def __init__(self):
        # NOTE: When I issue the operator from the Python console,
        # this print ends up there, and not in the terminal.
        print("Start")

    def __del__(self):
        print("End")

    def execute(self, context):
        # context.object.location.x = self.value / 100.0
        print("Execute; value: " + str(self.value))
        return {'FINISHED'}

    def modal(self, context, event):
        if event.type == 'MOUSEMOVE':  # Apply
            print("Mouse move: " + str(event.mouse_x) + ", " + str(event.mouse_y))
            self.value = event.mouse_x
            self.execute(context)
        elif event.type == 'LEFTMOUSE':  # Confirm
            print("Mouse left.")
            return {'FINISHED'}
        elif event.type in {'RIGHTMOUSE', 'ESC'}:  # Cancel
            print("Mouse right.")
            # context.object.location.x = self.init_loc_x
            return {'CANCELLED'}

        return {'RUNNING_MODAL'}

    def invoke(self, context, event):
        # NOTE: When I issue the operator from the Python console,
        # this print ends up there, and not in the terminal.
        print("Invoke")
        # self.init_loc_x = context.object.location.x
        self.value = event.mouse_x
        self.execute(context)

        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    @classmethod
    def poll(self, context):
        return (context.active_object is not None)

class CorridorProperty(PropertyGroup):
    pass

# bpy.ops.agnosia.dungeon_tools('INVOKE_DEFAULT')


class AddCorridorOperator(Operator):
    """bpy.ops.agnosia.dungeon_add_corridor"""
    bl_idname = "agnosia.dungeon_add_corridor"
    bl_label = "Create corridor"
    bl_options = {'REGISTER', 'UNDO'}

    # @classmethod
    # def poll(self, context):
    #     # TODO: do we actually need to limit this to object mode?
    #     return (context.mode == "OBJECT")

    def execute(self, context):
        # if context.mode != "OBJECT":
        #     self.report({'WARNING'}, "Create corridor: must be in Object mode.")
        #     return {'CANCELLED'}

        # Create a poly spline.
        bpy.ops.curve.primitive_bezier_curve_add(radius=0, view_align=False, enter_editmode=True, location=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0))
        bpy.ops.curve.spline_type_set(type='POLY', use_handles=False)

        # The spline starts with 2 points; move them apart to begin with.
        o = context.object
        curve = o.data
        spline = curve.splines[0]
        spline.points[0].co = Vector((0.0, 0.0, 0.0, 1.0))
        spline.points[1].co = Vector((10.0, 0.0, 0.0, 1.0))

        # FIXME: Make it a corridor.
        corridor = o.dungeon_corridors.add()

        ## FIXME: Activate the dungeon tools
        ## BUG: right now this swallows all input until it ends D:
        #bpy.ops.agnosia.dungeon_tools('INVOKE_DEFAULT')

        return {'FINISHED'}
