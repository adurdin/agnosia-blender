import bpy
import bmesh
import base64
import math
import mathutils
import random
import struct
import zlib

from array import array
from itertools import islice
from bpy.props import IntProperty, PointerProperty, StringProperty
from bpy.types import Object, Operator, Panel, PropertyGroup
from mathutils import Vector
from mathutils.bvhtree import BVHTree

#---------------------------------------------------------------------------#
# Operators

class AgnosiaCreatePointcloudOperator(Operator):
    bl_idname = "object.create_pointcloud"
    bl_label = "Create pointcloud"
    bl_options = {'REGISTER'}

    def execute(self, context):
        if context.mode != "OBJECT":
            self.report({'WARNING'}, "Create pointcloud: must be in Object mode.")
            return {'CANCELLED'}
        target = context.object
        if (target is None) or (target.type != 'MESH'):
            self.report({'WARNING'}, "Create pointcloud: must select a Mesh object.")
            return {'CANCELLED'}
        if target.pointclouds:
            self.report({'WARNING'}, "Create pointcloud: can't create a pointcloud from a pointcloud.")
            return {'CANCELLED'}

        # Deselect and hide the sampled object.
        target.select_set(False)
        target.hide_set(True)

        # Create a new pointcloud.
        o = create_pointcloud_from(context, target)

        # Make the pointcloud active, and select it.
        context.view_layer.objects.active = o
        o.select_set(True)

        # And begin updating the new pointcloud.
        bpy.ops.object.update_pointcloud()

        return {'FINISHED'}


class AgnosiaUpdatePointcloudOperator(Operator):
    bl_idname = "object.update_pointcloud"
    bl_label = "Update pointcloud"
    bl_options = set()

    _timer = None
    _generator = None
    _finished = False
    _cancelled = False
    _object = None

    # Class variable
    _running_on = {}

    def execute(self, context):
        self._object = context.object

        # Only allow one instance of the operator to run on any given object at a time.
        prior_op = self.__class__._running_on.get(self._object)
        if prior_op is not None:
            prior_op.abort()
        self.__class__._running_on[self._object] = self

        self._generator = update_pointcloud_iter(self._object)
        self._cancelled = False
        self._finished = False

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type in {'RIGHTMOUSE', 'ESC'}:
            self._cancelled = True

        if self._cancelled or self._finished:
            # Remove ourselves
            if self.__class__._running_on.get(self._object) == self:
                del self.__class__._running_on[self._object]
            # Remove the timer
            wm = context.window_manager
            wm.event_timer_remove(self._timer)
            self._timer = None

        if self._cancelled:
            return {'CANCELLED'}
        elif self._finished:
            return {'FINISHED'}
        elif event.type == 'TIMER':
            try:
                next(self._generator)
            except StopIteration:
                self._finished = True

        return {'PASS_THROUGH'}

    def abort(self):
        self._cancelled = True


class AgnosiaPointcloudExportOperator(Operator):
    bl_idname = "object.export_pointcloud"
    bl_label = "Export pointcloud"
    bl_options = {'REGISTER'}

    filepath : bpy.props.StringProperty(subtype="FILE_PATH")

    @classmethod
    def poll(cls, context):
        o = context.object
        return (
            (context.mode == 'OBJECT')
            and (o is not None)
            and (len(o.pointclouds) > 0)
            )

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        o = context.object
        pc = o.pointclouds[0]

        def to_uint8(f):
            return min(max(0, int(f * 255.0)), 255)

        with PointcloudBinWriter(self.filepath) as f:
            vertices = pc.raw_vertices
            normals = pc.raw_normals
            colors = pc.raw_colors
            def records():
                v_it = iter(vertices)
                n_it = iter(normals)
                c_it = iter(colors)
                while True:
                    v_xyz = list(islice(v_it, 3))
                    n_xyz = list(islice(n_it, 3))
                    c_rgb = [to_uint8(f) for f in list(islice(c_it, 4))][:3]
                    if v_xyz and c_rgb:
                        print(f"v: {v_xyz}, c: {c_rgb}")
                        yield v_xyz + c_rgb
                    else:
                        break
            for r in records():
                f.write(*r)

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
        box.prop(pc, 'target')
        box.prop(pc, 'point_count')
        box.prop(pc, 'seed')
        layout.operator('object.export_pointcloud', text="Export .bin")


#---------------------------------------------------------------------------#
# Pointcloud property and data

def _pointcloud_property_update(self, context):
    bpy.ops.object.update_pointcloud()

class PointcloudProperty(PropertyGroup):
    target : PointerProperty(name="Sample", type=Object, update=_pointcloud_property_update)
    point_count : IntProperty(name="Point count", default=1024, min=128, step=64, update=_pointcloud_property_update)
    seed : IntProperty(name="Seed", default=0, update=_pointcloud_property_update)
    raw_vertices_string : StringProperty(name="_RawVerticesString", default="")
    raw_normals_string : StringProperty(name="_RawNormalsString", default="")
    raw_colors_string : StringProperty(name="_RawColorsString", default="")
    _raw_cache = None

    @staticmethod
    def _pack_array(a):
        if a:
            b = a.tobytes()
            c = zlib.compress(b)
            d = base64.encodebytes(c)
            return d.decode('ascii')
        else:
            return ""

    @staticmethod
    def _unpack_array(s, typecode):
        if s:
            a = array(typecode)
            b = bytes(s, 'ascii')
            c = base64.decodebytes(b)
            d = zlib.decompress(c)
            a.frombytes(d)
            return a
        else:
            return array(typecode)

    @property
    def raw_cache(self):
        cache = self.__dict__.get('_raw_cache')
        if cache is None:
            cache = {}
            self.__dict__['_raw_cache'] = cache
        return cache

    @property
    def raw_vertices(self):
        if self.raw_vertices_string:
            value = self.raw_cache.get('vertices')
            if value is None:
                value = self._unpack_array(self.raw_vertices_string, 'f')
                self.raw_cache['vertices'] = value
            return value
        else:
            return array('f')

    @property
    def raw_normals(self):
        if self.raw_normals_string:
            value = self.raw_cache.get('normals')
            if value is None:
                value = self._unpack_array(self.raw_normals_string, 'f')
                self.raw_cache['normals'] = value
            return value
        else:
            return array('f')

    @property
    def raw_colors(self):
        if self.raw_colors_string:
            value = self.raw_cache.get('colors')
            if value is None:
                value = self._unpack_array(self.raw_colors_string, 'f')
                self.raw_cache['colors'] = value
            return value
        else:
            return array('f')

    def set_raw_data(self, vertices, normals=None, colors=None):
        if (not isinstance(vertices, array)) or (vertices.typecode != 'f'):
            raise ValueError("vertices must be type array('f')")
        if len(vertices) % 3 != 0:
            raise ValueError("vertices length must be multiple of 3")
        vertex_count = len(vertices) // 3
        if (normals is not None):
            if (not isinstance(normals, array)) or (normals.typecode != 'f'):
                raise ValueError("normals must be type array('f')")
            if len(normals) != (3 * vertex_count):
                raise ValueError("len(normals) must be 3 * vertex_count")
        if (colors is not None):
            if (not isinstance(colors, array)) or (colors.typecode != 'f'):
                raise ValueError("colors must be type array('f')")
            if len(colors) != 4 * vertex_count:
                raise ValueError("len(colors) must be 4 * vertex_count")

        self.raw_vertices_string = self._pack_array(vertices)
        self.raw_normals_string = self._pack_array(normals)
        self.raw_colors_string = self._pack_array(colors)

        # Cached
        self.raw_cache['vertices'] = vertices
        self.raw_cache['normals'] = normals
        self.raw_cache['colors'] = colors


#---------------------------------------------------------------------------#
# Material

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
    # centered with respect to all the other columns. Coordinates are +Y up, +X right.
    grid_size = 20.0
    def total_height(n):
        # Height of a node including its title bar. Not exact numbers, but good enough.
        return (20.0 if n.hide else (n.height + 30.0))
    column_location = Vector((0.0, 0.0)) # x: right edge, y: center.
    spacing = Vector((3.0, 2.0)) * grid_size
    for i, column in enumerate(all_columns):
        # Calculate the total size
        max_node_width = max(ceil(n.width) for n in column)
        total_node_height = sum(ceil(total_height(n)) for n in column)
        total_spacing = spacing[1] * (len(column) - 1)
        column_width = ceil(max_node_width / grid_size) * grid_size
        column_height = total_node_height + total_spacing
        # Lay out these nodes vertically down the column.
        x = column_location[0] - (column_width / 2.0)
        y = column_location[1] + (column_height / 2.0)
        for n in column:
            node_x = round(x - n.width / 2.0)
            node_y = y #round(y - total_height(n) / 2.0)
            n.location = Vector((node_x, node_y))
            y -= (ceil(total_height(n) + spacing[1]))
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

    # Get colors and normals from the vertex color layers.
    colors = nodes.new(type='ShaderNodeAttribute')
    colors.label = "PointColor Attribute"
    colors.attribute_name = 'PointColor'
    links.new(colors.outputs['Color'], diffuse.inputs['Color'])

    normals = nodes.new(type='ShaderNodeAttribute')
    colors.label = "PointNormal Attribute"
    normals.attribute_name = 'PointNormal'

    # Create nodes to unpack the normals from the second vertex color layer.
    combine = nodes.new(type='ShaderNodeCombineXYZ')
    combine.hide = True
    links.new(combine.outputs['Vector'], diffuse.inputs['Normal'])

    separate = nodes.new(type='ShaderNodeSeparateXYZ')
    separate.hide = True
    links.new(normals.outputs['Vector'], separate.inputs['Vector'])

    # Each of the X, Y, and Z channels needs (foo - 0.5) * 2.0
    for i in range(3):
        sub = nodes.new(type='ShaderNodeMath')
        sub.label = " - 0.5"
        sub.operation = 'SUBTRACT'
        sub.hide = True
        sub.inputs[1].default_value = 0.5
        links.new(separate.outputs[i], sub.inputs[0])
        mul = nodes.new(type='ShaderNodeMath')
        mul.label = " * 2.0"
        mul.operation = 'MULTIPLY'
        mul.hide = True
        mul.inputs[1].default_value = 2.0
        links.new(sub.outputs[0], mul.inputs[0])
        links.new(mul.outputs[0], combine.inputs[i])

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


#---------------------------------------------------------------------------#
# Pointcloud objects.

def create_pointcloud_from(context, target):
    o = create_empty_mesh_obj(context, 'Pointcloud')
    pc = o.pointclouds.add()
    pc.target = target
    pc.seed = random.randint(-2**31, 2**31)
    return o

def create_empty_mesh_obj(context, name):
    mesh = bpy.data.meshes.new(name + 'Mesh')
    o = bpy.data.objects.new(name, mesh)
    o.show_name = True
    context.scene.collection.objects.link(o)
    return o

def update_pointcloud_iter(o):
    if not o.pointclouds:
        return
    pc = o.pointclouds[0]
    target = pc.target
    if (target is None) or (target.type != 'MESH') or (target.pointclouds):
        return
    seed = pc.seed
    rng = random.Random(seed)
    for data in generate_points(pc.target, pc.point_count, rng, step_count=4096):
        yield

    vertices_arr = array('f', (f for vec in data[0] for f in vec))
    normals_arr = array('f', (f for vec in data[1] for f in vec))
    colors_arr = array('f', (f for vec in data[2] for f in vec))
    pc.set_raw_data(vertices_arr, normals=normals_arr, colors=colors_arr)

    o.data = create_pointcloud_mesh(o.data.name, data)
    assign_material(o, get_pointcloud_material())

def generate_points(target, count, rng=random, step_count=0):
    if not step_count: step_count = count
    total_count = 0
    total_data = [[], [], []]
    while total_count < count:
        step_count = min(step_count, (count - total_count))
        # data = sphere_sample_obj(target, step_count, rng)
        # data = volume_sample_obj(target, step_count, rng)
        data = surface_sample_obj(target, step_count, rng)
        for i in range(len(total_data)):
            total_data[i] += data[i]
        total_count += step_count
        if total_count < count:
            yield list(total_data)
    yield total_data

#---------------------------------------------------------------------------#
# Meshes for in-Blender visualization.

def create_pointcloud_mesh(name, data):
    mesh = bpy.data.meshes.new(name)
    (vertices, normals, colors) = data
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


def expand_vertex_data_to_mesh(vertices, normals, colors):
    expanded_vertices = []
    expanded_normals = []
    expanded_colors = []
    faces = []

    # Size of the mesh representing a point.
    scale = 0.05
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


#---------------------------------------------------------------------------#
# Sampling.

def sphere_sample_obj(o, count, rng):
    # Sample the object by raycasting from a sphere surrounding it
    # towards the origin.
    vertices = []
    normals = []
    colors = []
    radius = object_bounding_radius(o) + 0.1
    it = iter(sphere_surface_points(radius, rng))
    while len(vertices) < count:
        pt = next(it)
        result, position, normal, index = raycast_to_origin(o, pt)
        if result:
            vertices.append(position)
            normals.append(normal)
            colors.append((1.0, 0.0, 1.0, 1.0))
    return (vertices, normals, colors)

def volume_sample_obj(o, count, rng):
    # Sample the object by generating points within its bounds and
    # testing if they're inside it. Assumes the mesh is watertight.
    vertices = []
    normals = []
    colors = []
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bvh = BVHTree.FromBMesh(bm)

    halfwidth = object_bounding_halfwidth(o) + 0.1
    it = iter(cube_volume_points(halfwidth, rng))
    while len(vertices) < count:
        pt = next(it)

        (location, normal, index, distance) = raycast_to_exterior(bvh, pt)
        pt_is_inside = (location is not None)

        if pt_is_inside:
            vertices.append(location)
            normals.append(normal)
            # TEMP: color each point by its coordinates
            r = (abs(location[0]) / halfwidth)
            g = (abs(location[1]) / halfwidth)
            b = (abs(location[2]) / halfwidth)
            colors.append((r, g, b, 1.0))
    return (vertices, normals, colors)

def surface_sample_obj(o, count, rng):
    # Sample the object by generating points on the surfaces of its tris.
    vertices = []
    normals = []
    colors = []

    mesh = o.data
    # Find the surface area of each poly and the whole mesh.
    poly_areas = [p.area for p in mesh.polygons]
    surface_area = sum(poly_areas)

    # Generate uniform random area targets.
    area_targets = sorted(rng.uniform(0, surface_area) for _ in range(count))

    # Iterate the polys to see which reaches the target.
    area_so_far = 0
    target = area_targets.pop(0)
    for i, poly in enumerate(mesh.polygons):
        area_so_far += poly_areas[i]
        while target <= area_so_far:
            # Spawn a point.
            poly_vertices = [Vector(mesh.vertices[j].co) for j in poly.vertices]
            location = polygon_surface_point(poly_vertices, rng)
            normal = poly.normal
            # Save the point.
            vertices.append(location)
            normals.append(normal)
            # TEMP: color each point by its coordinates
            halfwidth = object_bounding_halfwidth(o) + 0.1
            r = (abs(location[0]) / halfwidth)
            g = (abs(location[1]) / halfwidth)
            b = (abs(location[2]) / halfwidth)
            colors.append((r, g, b, 1.0))
            # Get a new target
            if area_targets:
                target = area_targets.pop(0)
            else:
                # If we've run out of targets, then we have enough points.
                break
    if not vertices:
        print(f"ERROR: didn't generate any vertices!")
    return (vertices, normals, colors)

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

def sphere_surface_points(radius, rng):
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

def cube_volume_points(halfwidth, rng):
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

def polygon_surface_point(vertices, rng):
    # Return a random point on the surface of the polygon.
    # Determine the vertices abc of each triangle, and the vectors ab and ac.
    tris = [
        (
            vertices[0],    # a
            vertices[i+1],  # b
            vertices[i+2],  # c
            (vertices[i+1] - vertices[0]),  # ab
            (vertices[i+2] - vertices[0]),  # ac
        )
        for i in range(len(vertices) - 2)
    ]
    # Find the area of each tri and the total polygon area.
    tri_areas = [
        (ab.cross(ac)).length / 2.0
        for (_, _, _, ab, ac) in tris
    ]
    surface_area = sum(tri_areas)
    # Pick a target tri by area
    target = rng.uniform(0, surface_area)
    area_so_far = 0
    for (i, (a, b, c, ab, ac)) in enumerate(tris):
        area_so_far += tri_areas[i]
        while target <= area_so_far:
            # Pick a point in this tri
            r1 = rng.random()
            r2 = rng.random()
            r1root = math.sqrt(r1)
            pt = ((1 - r1root) * a
                + r1root * (1 - r2) * b
                + r1root * r2 * c)
            return pt
    # Shouldn't get here, but if we do, just return a vertex
    print("ERROR: failed to find target tri.")
    return vertices[0]

def raycast_to_origin(o, pt):
    # Raycast the object o from pt (in object space) to its origin.
    # Return a tuple: (result, position, normal, index)
    origin = Vector((0.0, 0.0, 0.0))
    direction = (origin - pt).normalized()
    return o.ray_cast(pt, direction)

def raycast_to_exterior(bvh, pt):
    """Raycast the BVHTree bvh from pt to the object's exterior.
    If pt is on the object's interior, return (location, normal, index, distance);
    if it's on the exterior, return (None, None, None, None)."""

    NO_HIT = (None, None, None, None)

    # If the point's too close to the origin, we can't get a proper direction,
    # so just skip it.
    origin = Vector((0, 0, 0))
    from_origin = (pt - origin)
    if (from_origin.length < 0.0001):
        return NO_HIT

    ray_origin = pt
    direction = from_origin.normalized()

    # Raycast from the point towards the exterior, iterating
    # until we don't hit any faces.
    tiny_step = (direction * 0.0001)
    first_outward = None
    outward_crossings = 0

    (location, normal, index, distance) = bvh.ray_cast(ray_origin, direction)
    if location is None:
        # Didn't hit anything, so we're done.
        return NO_HIT

    # Check if the face is oriented towards the ray or away from it.
    inward_facing = (direction.dot(normal) < 0)
    if inward_facing:
        # Must have been outside the object.
        return NO_HIT

    return (location, normal, index, distance)


#---------------------------------------------------------------------------#
# Pointcloud file types

## Structures in binary pointcloud file

def bin_size(size):
    return struct.pack('=L', size)

def bin_point(x, y, z, r, g, b):
    return struct.pack('=fffBBBx', x, y, z, r, g, b)


## Binary pointcloud writing

class PointcloudBinWriter:
    # File format:
    #     uint32_t size_of_data
    #     struct record {
    #         float x, y, z;
    #         uint8_t r, g, b;
    #         uint8_t pad;
    #     } records[size / sizeof(struct record)]

    def __init__(self, filename):
        self.filename = filename
        self.file = None
        self.count = 0
        self.size = 0

    def write(self, x, y, z, r, g, b):
        assert (self.file is not None), "File is not open."
        blob = bin_point(x, y, z, r, g, b)
        self.file.write(blob)
        self.size += len(blob)
        self.count += 1

    def __len__(self):
        return self.count

    def __enter__(self):
        self.file = open(self.filename, 'wb')
        # The file starts with the size of its data. We write a zero
        # initially, and fill in the actual size on __exit__().
        self.file.write(bin_size(0))
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if not exc_type and not exc_value:
            self.file.seek(0)
            self.file.write(bin_size(self.size))
        self.file.close()


#---------------------------------------------------------------------------#
# Utils.

from contextlib import contextmanager

@contextmanager
def tempfile(suffix='', dir=None):
    """ Context for temporary file.

    Will find a free temporary filename upon entering
    and will try to delete the file on leaving, even in case of an exception.

    Parameters
    ----------
    suffix : string
        optional file suffix
    dir : string
        optional directory to save temporary file in
    """
    # From: https://stackoverflow.com/a/29491523
    import os
    import tempfile as tmp

    tf = tmp.NamedTemporaryFile(delete=False, suffix=suffix, dir=dir)
    tf.file.close()
    try:
        yield tf.name
    finally:
        try:
            os.remove(tf.name)
        except OSError as e:
            if e.errno == 2:
                pass
            else:
                raise

@contextmanager
def file_atomic(filepath, *args, **kwargs):
    """ Open temporary file object that atomically moves to destination upon
    exiting.

    Allows reading and writing to and from the same filename.

    The file will not be moved to destination in case of an exception.

    Parameters
    ----------
    filepath : string
        the file path to be opened
    fsync : bool
        whether to force write the file to disk
    *args : mixed
        Any valid arguments for :code:`open`
    **kwargs : mixed
        Any valid keyword arguments for :code:`open`
    """
    # From: https://stackoverflow.com/a/29491523
    import os
    fsync = kwargs.get('fsync', False)

    with tempfile(dir=os.path.dirname(os.path.abspath(filepath))) as tmppath:
        with open(tmppath, *args, **kwargs) as file:
            try:
                yield file
            finally:
                if fsync:
                    file.flush()
                    os.fsync(file.fileno())
        os.rename(tmppath, filepath)