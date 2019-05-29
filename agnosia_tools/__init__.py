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
    imp.reload(pointcloud)
    print("agnosia_tools: reloaded.");
else:
    from . import pointcloud
    print("agnosia_tools: loaded.");


import bpy
from bpy.types import Panel


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


class AGNOSIA_PT_pointcloud(Panel):
    bl_label = "Pointcloud"
    bl_idname = "AGNOSIA_PT_pointcloud"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Agnosia"
    bl_context = "objectmode"

    @classmethod
    def poll(self, context):
        # This panel should only be available when the selected object
        # is a pointcloud.
        # FIXME: but for now it's always available!!
        return True

    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        box = row.box()
        box.label(text="There is nothing here that you recognise. Yet.");


#---------------------------------------------------------------------------#
# Menus

def menu_create_pointcloud(self, context):
    self.layout.operator(pointcloud.AgnosiaCreatePointcloudOperator.bl_idname)


#---------------------------------------------------------------------------#
# Register and unregister

def register():
    # Add operators
    bpy.utils.register_class(pointcloud.AgnosiaCreatePointcloudOperator)
    # Add panels
    bpy.utils.register_class(TOOLS_PT_agnosia_create)
    bpy.utils.register_class(AGNOSIA_PT_pointcloud)
    # Add menus
    # FIXME: this shouldn't just be slapped on the end of the menu like this!
    # Probably we should do an Add Object menu, and have this just be a convenience
    # to add a pointcloud + link it to the selected object for sampling.
    bpy.types.VIEW3D_MT_object.append(menu_create_pointcloud)
    # Done.
    print("agnosia_tools: registered.");

def unregister():
    # Remove menus
    bpy.types.VIEW3D_MT_object.remove(menu_create_pointcloud)
    # Remove panels
    bpy.utils.unregister_class(AGNOSIA_PT_pointcloud)
    bpy.utils.unregister_class(TOOLS_PT_agnosia_create)
    # Remove operators
    bpy.utils.unregister_class(pointcloud.AgnosiaCreatePointcloudOperator)
    # Done
    print("agnosia_tools: unregistered.");
