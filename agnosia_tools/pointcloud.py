import bpy
import bmesh
import math
import mathutils
import random

from bpy.props import IntProperty, PointerProperty
from bpy.types import Object, Operator, Panel, PropertyGroup
from mathutils import Vector
from mathutils.bvhtree import BVHTree

#---------------------------------------------------------------------------#
# Operators

class AgnosiaCreatePointcloudOperator(Operator):
    bl_idname = "object.create_pointcloud"
    bl_label = "Create pointcloud"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if bpy.context.mode != "OBJECT":
            self.report({'WARNING'}, "Create pointcloud: must be in Object mode.")
            return {'CANCELLED'}
        target = bpy.context.object
        if (target is None) or (target.type != 'MESH'):
            self.report({'WARNING'}, "Create pointcloud: must select a Mesh object.")
            return {'CANCELLED'}
        if target.pointclouds:
            self.report({'WARNING'}, "Create pointcloud: can't create a pointcloud from a pointcloud.")
            return {'CANCELLED'}

        # Create a pointcloud.
        o = create_pointcloud_from(context, target)

        # Make the pointcloud active, and select it.
        bpy.context.view_layer.objects.active = o
        o.select_set(True)

        # Deselect and hide the sampled object.
        target.select_set(False)
        target.hide_set(True)

        return {'FINISHED'}


#---------------------------------------------------------------------------#
# Panels

class AGNOSIA_PT_pointcloud(Panel):
    bl_label = "Pointcloud"
    bl_idname = "AGNOSIA_PT_pointcloud"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Agnosia"
    bl_context = "objectmode"

    @classmethod
    def poll(self, context):
        o = context.object
        if o is None: return False
        if not o.select_get(): return False
        if not o.pointclouds: return False
        return True

    def draw(self, context):
        o = context.object
        pc = o.pointclouds[0]

        layout = self.layout
        row = layout.row(align=True)
        box = row.box()
        box.label(text="There is nothing here that you recognise. Yet.");
        box = layout.box()
        box.prop(pc, 'obj_to_sample')
        box.prop(pc, 'point_count')


#---------------------------------------------------------------------------#
# Properties

def update(self, context):
    self.update(context)

class PointcloudProperty(PropertyGroup):
    obj_to_sample : PointerProperty(name="Sample", type=Object, update=update)
    point_count : IntProperty(name="Point count", default=1024, min=128, max=65536, step=64, update=update)

    def update(self, context):
        o = context.object
        if not o.pointclouds: return
        update_pointcloud(context, o)


#---------------------------------------------------------------------------#
# Core

def create_pointcloud_from(context, target=None):
    o = create_empty_mesh_obj(context, 'Pointcloud')
    o.pointclouds[0].obj_to_sample = target
    update_pointcloud(context, o)
    return o

def create_empty_mesh_obj(context, name):
    mesh = bpy.data.meshes.new(name + 'Mesh')
    o = bpy.data.objects.new(name, mesh)
    o.show_name = True
    context.scene.collection.objects.link(o)
    o.pointclouds.add()
    return o

def create_pointcloud_mesh(context, name, sampler, count, target):
    mesh = bpy.data.meshes.new(name)
    (vertices, normals) = sampler(count)
    if vertices:
        mesh.from_pydata(vertices, [], [])
        # This is supposed to set normals, but I can't get it to work:
        # blender won't show them in edit mode, nor will it export them.
        # Seems like per-vertex normals only actually work if you have edges/faces?
        mesh.normals_split_custom_set_from_vertices(normals)
        mesh.validate(verbose=True, clean_customdata=False)
        mesh.update()
    return mesh

def update_pointcloud(context, o):
    pc = o.pointclouds[0]
    target = pc.obj_to_sample
    if not target:
        return False
    def sampler(count):
        # return sphere_sample_obj(target, count)
        return volume_sample_obj(context, target, count)
    o.data = create_pointcloud_mesh(context, o.data.name, sampler, pc.point_count, target)
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
    # Raycast the object o from pt (in object space) to its origin.
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

def raycast_to_exterior(bvh, pt, direction):
    """Raycast the BVHTree bvh from pt to the object's exterior.
    If pt is on the object's interior, return (location, normal, index, distance);
    if it's on the exterior, return (None, None, None, None).

    Because Blender's raycast only reports the first hit, this can sometimes
    return false positives. Do two different raycasts in two perpendicular
    directions if you need more certainty."""

    ray_origin = pt
    direction = direction.normalized()

    # Raycast from the point towards the exterior, iterating
    # until we don't hit any faces.
    tiny_step = (direction * 0.0001)
    previous_index = -1
    first_outward = None
    outward_crossings = 0
    while True:
        (location, normal, index, distance) = bvh.ray_cast(ray_origin, direction)
        if location is None:
            # Didn't hit anything, so we're done.
            break

        # Sanity check that we're not hitting the same face again due to rounding error!
        if index == previous_index:
            ray_origin = location + tiny_step
            continue
        previous_index = index

        # Check if the face is oriented towards the ray or away from it.
        inward_facing = (direction.dot(normal) < 0)
        if inward_facing:
            outward_crossings -= 1
        else:
            outward_crossings += 1
            if first_outward is None:
                first_outward = (location, normal, index, distance)

        # Do the next raycast from just beyond the hit point.
        ray_origin = location + tiny_step

    pt_is_inside = (outward_crossings > 0)
    if pt_is_inside:
        return first_outward
    else:
        return (None, None, None, None)

def volume_sample_obj(context, o, count):
    # Sample the object by generating points within its bounds and
    # testing if they're inside it. Assumes the mesh is watertight.
    vertices = []
    normals = []
    # FIXME: Should this be FromMesh(o.data) instead??
    #        Why FromObject, does it include children? if so, nice.
    bvh = BVHTree.FromObject(o, context.depsgraph)
    # bm = bmesh.new()
    # bm.from_mesh(o.data)
    # bvh = BVHTree.FromBMesh(bm)

    radius = object_bounding_radius(o) + 0.1
    halfwidth = object_bounding_halfwidth(o) + 0.1
    it = iter(cube_volume_points(halfwidth))
    while len(vertices) < count:
        pt = next(it)

        # Two raycasts reduce the number of erroneous points.
        hit0 = raycast_to_exterior(bvh, pt, Vector((1, 0, 0)))
        hit1 = raycast_to_exterior(bvh, pt, Vector((0, 1, 0)))
        pt_is_inside = (hit0[0] is not None and hit1[0] is not None)

        if pt_is_inside:
            vertices.append(pt)
            normals.append(Vector((1, 0, 0)))
    return (vertices, normals)


def test_bvh_raycast(o, count):
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bvh = BVHTree.FromBMesh(bm)
    start = Vector((10, 0, 0))
    direction = Vector((-1, 0, 0))

    fail = 20
    while fail > 0:
        (location, normal, index, distance) = bvh.ray_cast(start, direction)
        if location is None:
            print("Raycast did not hit anything.")
            break
        else:
            print(f"Hit at {location}, normal {normal}, index {index}, distance {distance}.")
            start += direction * (distance * 1.01)
        # Just ensure we stop sometime
        fail -= 1
    return ([], [])

    # Okay, bvh raycast hits faces going in either direciton. We can dot the normal to see
    # if it's inward or outward.

    # Hit at <Vector (1.0000, 0.0000, 0.0000)>,
    #     normal <Vector (1.0000, -0.0000, 0.0000)>,
    #     index 4, distance 9.0.
    # Hit at <Vector (-1.0000, 0.0000, 0.0000)>,
    #     normal <Vector (-1.0000, -0.0000, 0.0000)>,
    #     index 2, distance 1.9099998474121094.
