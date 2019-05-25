import bpy
import bmesh
import math
import mathutils
import random
from mathutils import Vector

def create_mesh_obj(name, verts):
    mesh = bpy.data.meshes.new(name+'Mesh')
    obj = bpy.data.objects.new(name, mesh)
    obj.show_name = True
    bpy.context.scene.collection.objects.link(obj)
    mesh.from_pydata(verts, [], [])
    mesh.validate(verbose=True, clean_customdata=False)
    mesh.update()
    return obj

def calculate_radius(o):
    from math import sqrt
    radius = 0.0
    for (x, y, z) in o.bound_box:
        radius = max(radius, sqrt(x*x + y*y + z*z))
    return radius

def sphere_surface_points(radius, count, rng=random):
    from math import acos, cos, pi, sin, sqrt
    for i in range(count):
        u = rng.random()
        v = rng.random()
        theta = 2 * pi * u
        phi = acos(2 * v - 1)
        x = radius * cos(theta) * sin(phi)
        y = radius * sin(theta) * sin(phi)
        z = radius * cos(phi)
        yield Vector((x, y, z))

def create_pointcloud_from_active_object():
    o = bpy.context.active_object
    if not o: raise Exception("No object selected")

    count = 5000
    points = []

    # Sample the object spherically, uniformly.
    origin = Vector((0.0, 0.0, 0.0))
    radius = calculate_radius(o) + 1.0
    for pt in sphere_surface_points(radius, count):
        direction = (origin - pt).normalized()
        (result, position, normal, index) = o.ray_cast(pt, direction)
        if result:
            points.append(position)

    cloud = create_mesh_obj(o.name + '_cloud', points)
    cloud.select_set(True)
    o.hide_set(True)
    print(f"Created: {cloud}")
