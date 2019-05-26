import bpy
import bmesh
import math
import mathutils
import random
from mathutils import Vector

def create_mesh_obj(name, vertices, normals):
    mesh = bpy.data.meshes.new(name + 'Mesh')
    o = bpy.data.objects.new(name, mesh)
    o.show_name = True
    bpy.context.scene.collection.objects.link(o)
    mesh.from_pydata(vertices, [], [])
    mesh.calc_normals()
    # This is supposed to set normals, but I can't get it to work.
    # mesh.normals_split_custom_set_from_vertices(normals)
    mesh.validate(verbose=True, clean_customdata=False)
    mesh.update()
    return o

def calculate_radius(o):
    from math import sqrt
    radius = 0.0
    for (x, y, z) in o.bound_box:
        radius = max(radius, sqrt(x*x + y*y + z*z))
    return radius

def sphere_surface_points(radius, count, rng=random):
    # Yield an iterable of Vector randomly distributed
    # on the surface of a sphere with the given radius.
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

def cube_volume_points(halfwidth, count, rng=random):
    # Yield an iterable of Vector randomly distributed
    # within the volume of a cube with the given halfwidth.
    for i in range(count):
        u = rng.random()
        v = rng.random()
        w = rng.random()
        x = halfwidth * u
        y = halfwidth * v
        z = halfwidth * w
        yield Vector((x, y, z))

def raycast_to_origin(o, pt):
    # Raycast the object o from pt (in object space) to the origin.
    # Return a tuple: (result, position, normal, index)
    origin = Vector((0.0, 0.0, 0.0))
    direction = (origin - pt).normalized()
    return o.ray_cast(pt, direction)

def create_pointcloud_from_active_object():
    o = bpy.context.active_object
    if not o: raise Exception("No object selected")

    count = 5000
    vertices = []
    normals = []

    # Sample the object spherically, uniformly.
    radius = calculate_radius(o) + 1.0
    for pt in sphere_surface_points(radius, count):
        result, position, normal, index = raycast_to_origin(o, pt)
        if result:
            vertices.append(position)
            normals.append(normal)

    cloud = create_mesh_obj(o.name + '_cloud', vertices, normals)
    cloud.select_set(True)
    o.hide_set(True)
    print(f"Created: {cloud}")
