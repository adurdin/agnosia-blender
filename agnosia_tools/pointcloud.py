import bpy
import bmesh
from mathutils import Vector

def create_vertices(name, verts):
    mesh = bpy.data.meshes.new(name+'Mesh')
    obj = bpy.data.objects.new(name, mesh)
    obj.show_name = True
    bpy.context.scene.collection.objects.link(obj)
    mesh.from_pydata(verts, [], [])
    mesh.update()
    return obj

def get_face_centers(mesh_obj):
    mesh = mesh_obj.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    face_positions = []
    for face in bm.faces:
        position_in_object = face.calc_center_median() 
        face_positions.append(mesh_obj.matrix_world @ position_in_object)
    return face_positions

def create_pointcloud_from_active_object():
    obj = bpy.context.active_object
    face_positions = get_face_centers(obj)
    pointcloud = create_vertices(obj.name + '_pointcloud', face_positions)
    print(f"Created: {pointcloud}")
