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
    # This is supposed to set normals, but I can't get it to work:
    # blender won't show them in edit mode, nor will it export them.
    # Seems like per-vertex normals only actually work if you have edges/faces?
    mesh.normals_split_custom_set_from_vertices(normals)
    mesh.validate(verbose=True, clean_customdata=False)
    mesh.update()
    return o

def object_bounding_radius(o):
    from math import sqrt
    radius = 0.0
    for (x, y, z) in o.bound_box:
        radius = max(radius, sqrt(x*x + y*y + z*z))
    return radius

def object_bounding_halfwidth(o):
    halfwidth = 0.0
    for (x, y, z) in o.bound_box:
        halfwidth = max(halfwidth, abs(x), abs(y), abs(z))
    return halfwidth

def sphere_surface_points(radius, rng=random):
    # Generate Vectors randomly distributed on the surface of
    # a sphere with the given radius.
    while True:
        from math import acos, cos, pi, sin, sqrt
        u = rng.random()
        v = rng.random()
        theta = 2 * pi * u
        phi = acos(2 * v - 1)
        x = radius * cos(theta) * sin(phi)
        y = radius * sin(theta) * sin(phi)
        z = radius * cos(phi)
        yield Vector((x, y, z))

def cube_volume_points(halfwidth, rng=random):
    # Generate Vectors randomly distributed within the volume
    # of a cube with the given halfwidth.
    while True:
        u = rng.uniform(-1, 1)
        v = rng.uniform(-1, 1)
        w = rng.uniform(-1, 1)
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

def sphere_sample_obj(o, count):
    # Sample the object by raycasting from a sphere surrounding it
    # towards the origin.
    vertices = []
    normals = []
    radius = object_bounding_radius(o) + 0.1
    it = iter(sphere_surface_points(radius))
    while len(vertices) < count:
        pt = next(it)
        result, position, normal, index = raycast_to_origin(o, pt)
        if result:
            vertices.append(position)
            normals.append(normal)
    return (vertices, normals)

def volume_sample_obj(o, count):
    # Sample the object by generating points within its bounds and
    # testing if they're inside it.
    vertices = []
    normals = []
    halfwidth = object_bounding_halfwidth(o) + 0.1
    it = iter(cube_volume_points(halfwidth))
    while len(vertices) < count:
        pt = next(it)
        # FIXME: need to check if this point is inside the object or outside.
        # Thinking can raycast from pt in the direction of (pt - origin) and
        # a large distance, and see if we only cross outward-facing faces...
        # But object raycast only returns the first hit... don't even know if
        # that includes outward-facing faces.
        vertices.append(pt)
        normals.append(Vector((1, 0, 0)))
    return (vertices, normals)

def create_pointcloud_from_active_object():
    o = bpy.context.active_object
    if not o: raise Exception("No object selected")

    count = 5000
    (vertices, normals) = sphere_sample_obj(o, count)
    # (vertices, normals) = volume_sample_obj(o, count)

    cloud = create_mesh_obj(o.name + '_cloud', vertices, normals)
    cloud.select_set(True)
    o.hide_set(True)
    print(f"Created: {cloud}")
