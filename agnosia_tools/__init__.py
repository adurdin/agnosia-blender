bl_info = {
    'name': 'Create Pointcloud',
    'author': 'vfig',
    'version': (0, 0, 1),
    'blender': (2, 80, 0),
    'category': '(Development)',
    'description': '(in development)'
}

if "bpy" in locals():
    import importlib as imp
    imp.reload(dungeon)
    imp.reload(pointcloud)
    print("agnosia_tools: reloaded.");
else:
    from . import dungeon
    from . import pointcloud
    print("agnosia_tools: loaded.");


import bpy
from bpy.props import CollectionProperty
from bpy.types import Panel

from .pointcloud import PointcloudProperty


#---------------------------------------------------------------------------#
# Panels

class TOOLS_PT_agnosia_create(Panel):
    bl_label = "Agnosia"
    bl_idname = "TOOLS_PT_agnosia_create"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Create"
    bl_context = "objectmode"

    @classmethod
    def poll(self, context):
        # This panel should always be available.
        return True

    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        box = row.box()
        box.label(text="Create")
        row = box.row(align=True)
        row.operator("object.create_pointcloud", text="Pointcloud")


#---------------------------------------------------------------------------#
# Menus

def menu_create_pointcloud(self, context):
    self.layout.operator(pointcloud.AgnosiaCreatePointcloudOperator.bl_idname)


#---------------------------------------------------------------------------#
# Register and unregister

def register():
    # Add operators
    bpy.utils.register_class(pointcloud.AgnosiaCreatePointcloudOperator)
    bpy.utils.register_class(pointcloud.AgnosiaUpdatePointcloudOperator)
    bpy.utils.register_class(pointcloud.AgnosiaPointcloudExportOperator)
    bpy.utils.register_class(dungeon.ToolsOperator)
    bpy.utils.register_class(dungeon.AddCorridorOperator)
    bpy.utils.register_class(dungeon.BuildCorridorMeshOperator)

    # Add panels
    bpy.utils.register_class(TOOLS_PT_agnosia_create)
    bpy.utils.register_class(pointcloud.AGNOSIA_PT_pointcloud)
    bpy.utils.register_class(dungeon.AGNOSIA_PT_dungeon_corridor)

    # Add menus
    # FIXME: this shouldn't just be slapped on the end of the menu like this!
    # Probably we should do an Add Object menu, and have this just be a convenience
    # to add a pointcloud + link it to the selected object for sampling.
    bpy.types.VIEW3D_MT_object.append(menu_create_pointcloud)

    # Add property groups
    bpy.utils.register_class(dungeon.CorridorProperty)
    bpy.types.Object.dungeon_corridors = CollectionProperty(type=dungeon.CorridorProperty)
    bpy.utils.register_class(pointcloud.PointcloudProperty)
    # FIXME: Object.pointclouds should maybe be on Mesh instead, since I can't sample cameras and shit.
    bpy.types.Object.pointclouds = CollectionProperty(type=pointcloud.PointcloudProperty)

    # Done.
    print("agnosia_tools: registered.");


def unregister():
    # Remove property groups
    del bpy.types.Object.pointclouds
    bpy.utils.unregister_class(pointcloud.PointcloudProperty)
    del bpy.types.Object.dungeon_corridors
    bpy.utils.unregister_class(dungeon.CorridorProperty)

    # Remove menus
    bpy.types.VIEW3D_MT_object.remove(menu_create_pointcloud)

    # Remove panels
    bpy.utils.unregister_class(dungeon.AGNOSIA_PT_dungeon_corridor)
    bpy.utils.unregister_class(pointcloud.AGNOSIA_PT_pointcloud)
    bpy.utils.unregister_class(TOOLS_PT_agnosia_create)

    # Remove operators
    bpy.utils.unregister_class(dungeon.BuildCorridorMeshOperator)
    bpy.utils.unregister_class(dungeon.AddCorridorOperator)
    bpy.utils.unregister_class(dungeon.ToolsOperator)
    bpy.utils.unregister_class(pointcloud.AgnosiaPointcloudExportOperator)
    bpy.utils.unregister_class(pointcloud.AgnosiaUpdatePointcloudOperator)
    bpy.utils.unregister_class(pointcloud.AgnosiaCreatePointcloudOperator)

    # Done
    print("agnosia_tools: unregistered.");
