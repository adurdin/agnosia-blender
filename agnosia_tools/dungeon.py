import bpy
import mathutils

from bpy.types import Object, Operator, Panel, PropertyGroup
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
    # def poll(cls, context):
    #     # TODO: do we actually need to limit this to object mode?
    #     return (context.mode == "OBJECT")

    def execute(self, context):
        # if context.mode != "OBJECT":
        #     self.report({'WARNING'}, "Create corridor: must be in Object mode.")
        #     return {'CANCELLED'}

        name = 'Corridor'

        # Create a poly spline with two points.
        curve = bpy.data.curves.new(name=(name + '_curve'), type='CURVE')
        curve.dimensions = '3D'
        spline = curve.splines.new(type='POLY')
        needed_point_count = (2 - len(spline.points))
        if needed_point_count > 0:
            spline.points.add(count=needed_point_count)
        spline.points[0].co = Vector((0.0, 0.0, 0.0, 1.0))
        spline.points[1].co = Vector((10.0, 0.0, 0.0, 1.0))

        # Create an object to hold the spline.
        o = bpy.data.objects.new(name, curve)

        # Make it a corridor.
        corridor = o.dungeon_corridors.add()

        # FIXME: set corridor properties
        # FIXME: derive a mesh from the corridor curve??

        # Add the object to the scene, make it active, and select it.
        context.scene.collection.objects.link(o)
        context.view_layer.objects.active = o
        o.select_set(True)

        # FIXME: enter edit mode?

        ## FIXME: Activate the dungeon tools
        ## BUG: right now this swallows all input until it ends D:
        #bpy.ops.agnosia.dungeon_tools('INVOKE_DEFAULT')

        return {'FINISHED'}

class BuildCorridorMeshOperator(Operator):
    """bpy.ops.agnosia.dungeon_build_corridor_mesh"""
    bl_idname = "agnosia.dungeon_build_corridor_mesh"
    bl_label = "Build corridor mesh"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        o = context.object
        if context.mode != "OBJECT": return False
        if o is None: return False
        if not o.select_get(): return False
        if not o.dungeon_corridors: return False
        return True

    def execute(self, context):
        print("FIXME: make a mesh here, somehow")

        return {'FINISHED'}


#---------------------------------------------------------------------------#
# Panels

class AGNOSIA_PT_dungeon_corridor(Panel):
    bl_label = "Corridor"
    bl_idname = "AGNOSIA_PT_dungeon_corridor"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Agnosia"
    bl_context = "objectmode"

    @classmethod
    def poll(cls, context):
        o = context.object
        if context.mode != "OBJECT": return False
        if o is None: return False
        if not o.select_get(): return False
        if not o.dungeon_corridors: return False
        return True

    def draw(self, context):
        o = context.object

        layout = self.layout
        layout.operator('agnosia.dungeon_build_corridor_mesh', text="Build mesh")
