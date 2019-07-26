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
