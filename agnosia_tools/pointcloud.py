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

UNPACK_NORMALS_SCRIPT = """\
    shader unpack_normals(
        vector PackedNormal = vector(0, 0, 0),
        output vector Normal = vector(0, 0, 0))
    {
        vector v = PackedNormal.xyz;
        v -= vector(0.5, 0.5, 0.5);
        v *= 2.0;
        Normal = v;
    }
"""

def layout_nodes(node_tree, root_node):
    """Make all the nodes in node_tree, starting from root_node, nice and tidy."""
    from collections import defaultdict
    from math import ceil

    # Lookup table of nodes to their incoming links
    incoming = defaultdict(list)
    for l in node_tree.links:
        incoming[l.to_node].append(l)

    # Lookup table of nodes to their sort keys
    sort_keys = {}
    sort_keys[root_node] = ('_root',)

    all_columns = [[root_node]]
    links = list(incoming[root_node])

    # Arrange all the nodes from the root nodes into columns,
    # with each column's nodes in order by the outputs and nodes they feed into.
    while links:
        # Drop all the nodes on all the links into this column
        column = []
        for l in links:
            # k = ((l.to_socket.name, l.from_socket.name), ) + sort_keys[l.to_node]
            k = (l.to_socket.name, ) + sort_keys[l.to_node]
            other_k = sort_keys.get(l.from_node, None)
            if other_k is not None:
                k = max(k, other_k)
            sort_keys[l.from_node] = k
            if l.from_node not in column:
                column.append(l.from_node)
        column.sort(key=sort_keys.get)
        all_columns.append(column)
        # Get the next set of links to sort
        links = []
        for n in column:
            links.extend(incoming[n])

    # Now lay out all the nodes right-to-left, with each column vertically
    # centered with respect to all the other columns.
    grid_size = 20.0
    title_height = grid_size
    column_location = Vector((0.0, 0.0)) # x: right edge, y: center.
    spacing = Vector((4.0, 2.0)) * grid_size
    for i, column in enumerate(all_columns):
        # Calculate the total size
        total_node_width = max(ceil(n.width) for n in column)
        total_node_height = sum(ceil(n.height + title_height) for n in column)
        padding = spacing[1] * (len(column) - 1)
        column_width = ceil(total_node_width / grid_size) * grid_size
        column_height = total_node_height + padding
        # Lay out these nodes vertically down the column.
        x = column_location[0] - (column_width / 2.0)
        y = column_location[1] + (column_height / 2.0)
        for n in column:
            node_x = round(x - n.width / 2.0)
            node_y = round(y - (n.height + title_height) / 2.0)
            n.location = Vector((node_x, node_y))
            y -= (ceil(n.height + title_height + spacing[1]))
        column_location[0] -= (column_width + spacing[0])

def define_pointcloud_material(material):
    material.use_nodes = True

    tree = material.node_tree
    nodes = tree.nodes
    links = tree.links

    nodes.clear()

    output = nodes.new(type='ShaderNodeOutputMaterial')
    # output.location = self._grid_location(6, 4)

    diffuse = nodes.new(type='ShaderNodeBsdfDiffuse')
    diffuse.inputs['Color'].default_value = (1.0, 1.0, 1.0, 1.0)
    diffuse.inputs['Roughness'].default_value = 0.5
    links.new(diffuse.outputs['BSDF'], output.inputs['Surface'])

    colors = nodes.new(type='ShaderNodeAttribute')
    colors.attribute_name = 'PointColor'
    links.new(colors.outputs['Color'], diffuse.inputs['Color'])

    text = bpy.data.texts.new(name='UnpackNormalsNode')
    text.from_string(UNPACK_NORMALS_SCRIPT)
    unpack_normals = nodes.new(type='ShaderNodeScript')
    unpack_normals.label = "Unpack Normals"
    unpack_normals.mode = 'INTERNAL'
    unpack_normals.script = text
    unpack_normals.inputs.new(name='Packed Normal', type='NodeSocketVectorXYZ')
    unpack_normals.outputs.new(name='Normal', type='NodeSocketVectorXYZ')
    links.new(unpack_normals.outputs['Normal'], diffuse.inputs['Normal'])

    normals = nodes.new(type='ShaderNodeAttribute')
    normals.attribute_name = 'PointNormal'
    links.new(normals.outputs['Vector'], unpack_normals.inputs['Packed Normal'])

    layout_nodes(tree, output)

def get_pointcloud_material():
    name = 'PointcloudMaterial'
    m = bpy.data.materials.get(name)
    if not m:
        m = bpy.data.materials.new(name)
        define_pointcloud_material(m);
    return m

def assign_material(o, mat):
    if (o.data.materials):
        o.data.materials[0] = mat
    else:
        o.data.materials.append(mat)

def create_pointcloud_from(context, target):
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
    (vertices, normals, colors) = sampler(count)
    # Expand each vertex to make a quad facing the -y axis.
    if vertices:
        (vertices, faces, normals, colors) = \
            expand_vertex_data_to_mesh(vertices, normals, colors)
        mesh.from_pydata(vertices, [], faces)
        mesh.validate(verbose=True, clean_customdata=False)
        mesh.update()
        # Apply per-vertex colors and normals
        color_layer = mesh.vertex_colors.new(name='PointColor')
        for (i, color) in enumerate(colors):
            color_layer.data[i].color = color
        normal_layer = mesh.vertex_colors.new(name='PointNormal')
        for (i, normal) in enumerate(normals):
            # Pack the normals into the color data
            n = (normal / 2.0) + Vector((0.5, 0.5, 0.5))
            normal_layer.data[i].color = (n[0], n[1], n[2], 0.0)
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
    assign_material(o, get_pointcloud_material())
    return o

def expand_vertex_data_to_mesh(vertices, normals, colors):
    expanded_vertices = []
    expanded_normals = []
    expanded_colors = []
    faces = []

    scale = 0.01
    quad = (
        Vector((1, 0, 1)) * scale,
        Vector((-1, 0, 1)) * scale,
        Vector((-1, 0, -1)) * scale,
        Vector((1, 0, -1)) * scale,
        )

    # Expand the source data to a quad.
    for v in vertices:
        expanded_vertices.extend((v + quad[0], v + quad[1], v + quad[2], v + quad[3]))
    for n in normals:
        expanded_normals.extend((n, n, n, n))
    for c in colors:
        expanded_colors.extend((c, c, c, c))

    # Generate faces
    for i in range(len(vertices)):
        base = (4 * i)
        faces.append((
            base + 0,
            base + 1,
            base + 2,
            base + 3,
            ))

    return (expanded_vertices, faces, expanded_normals, expanded_colors)

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
    colors = []
    radius = object_bounding_radius(o) + 0.1
    it = iter(sphere_surface_points(radius))
    while len(vertices) < count:
        pt = next(it)
        result, position, normal, index = raycast_to_origin(o, pt)
        if result:
            vertices.append(position)
            normals.append(normal)
            colors.append((1.0, 0.0, 1.0, 1.0))
    return (vertices, normals, colors)

def raycast_to_exterior(bvh, pt, direction):
    """Raycast the BVHTree bvh from pt to the object's exterior.
    If pt is on the object's interior, return (location, normal, index, distance);
    if it's on the exterior, return (None, None, None, None).

    Because Blender's raycast only reports the first hit, this can sometimes
    return false positives. Do two different raycasts in two perpendicular
    directions if you need more certainty."""

    origin = Vector((0, 0, 0))
    from_origin = (pt - origin)
    # If the point's too close to the origin, we can't get a proper direction,
    # so just skip it.
    if (from_origin.length < 0.0001):
        return (None, None, None, None)

    ray_origin = pt
    direction = from_origin.normalized()

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
    colors = []
    # FIXME: Should this be FromMesh(o.data) instead??
    #        Why FromObject, does it include children? if so, nice.
    bvh = BVHTree.FromObject(o, context.depsgraph)
    # bm = bmesh.new()
    # bm.from_mesh(o.data)
    # bvh = BVHTree.FromBMesh(bm)

    halfwidth = object_bounding_halfwidth(o) + 0.1
    it = iter(cube_volume_points(halfwidth))
    while len(vertices) < count:
        pt = next(it)

        # Two raycasts reduce the number of erroneous points.
        hit0 = raycast_to_exterior(bvh, pt, Vector((1, 0, 0)))
        # hit1 = raycast_to_exterior(bvh, pt, Vector((0, 1, 0)))
        # pt_is_inside = (hit0[0] is not None and hit1[0] is not None)
        pt_is_inside = hit0[0] is not None

        if pt_is_inside:
            surface_pt = hit0[0]
            surface_normal = hit0[1]
            vertices.append(pt)
            normals.append(surface_normal)
            # TEMP: color each point by its coordinates
            r = (abs(pt[0]) / halfwidth)
            g = (abs(pt[1]) / halfwidth)
            b = (abs(pt[2]) / halfwidth)
            colors.append((r, g, b, 1.0))
    return (vertices, normals, colors)
