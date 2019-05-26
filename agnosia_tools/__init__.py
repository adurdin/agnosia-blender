bl_info = {
    'name': 'Create Pointcloud',
    'author': 'vfig',
    'version': (0, 0, 1),
    'blender': (2, 80, 0),
    'category': '(Development)',
    'description': '(in development)'
}

# Load/reload the entire package.
is_reloading = ("bpy" in locals())
import bpy, importlib
if is_reloading:
    importlib.reload(pointcloud)
else:
    from . import pointcloud

class ObjectCreatePointcloudOperator(bpy.types.Operator):
    bl_idname = "dev.create_pointcloud"
    bl_label = "Create pointcloud"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        pointcloud.create_pointcloud_from_active_object()
        return {'FINISHED'}

def menu_func(self, context):
    self.layout.operator(ObjectCreatePointcloudOperator.bl_idname)

def register():
    bpy.utils.register_class(ObjectCreatePointcloudOperator)
    bpy.types.VIEW3D_MT_object.append(menu_func)
    print("-" * 80)
    print(f"{bl_info['name']} add-on loaded.")

def unregister():
    bpy.utils.unregister_class(ObjectCreatePointcloudOperator)
