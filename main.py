bl_info = {
    "name": "Vertex Alpha Tool",
    "author": "JDS",
    "version": (1, 0),
    "blender": (2, 92, 0),
    "location": "Vertex Paint | View3D > N panel > Tool > Vertex Alpha Tool",
    "description": "Minimalist add-on to augment manipulation of vertex colours",
    "warning": "Experimental Build",
    "wiki_url": "",
    "tracker_url": "",
    "category": "Paint"    
}

import bpy, bmesh, numpy as np
from typing import List
from mathutils import Vector

class AlphaToolPropsGroup(bpy.types.PropertyGroup):
    
    def vc_layer_items(self, context):
            mesh = context.object.data
            return [] if not mesh.vertex_colors else [(vc_layer.name,
                vc_layer.name, "") for vc_layer in mesh.vertex_colors]
    
    def vc_channel_items(self, context):
            channels = ("r", "g", "b", "a")
            return [(channel, channel.upper(), "") for channel in channels]
    
    vertex_colours : bpy.props.StringProperty(name="Vertex Colours")
    
    alpha_constant: bpy.props.FloatProperty(
        name = "Alpha",
        description = "Constant value for the alpha channel",
        default = 0.0,
        soft_min = 0.0,
        soft_max = 1.0,
        precision = 3,
        subtype = 'FACTOR'
    )
    
    src_vc_layer: bpy.props.EnumProperty(
        name="Source Layer",
        items=vc_layer_items,
        description="Source vertex colour layer"
    )
    
    src_vc_channel: bpy.props.EnumProperty(
        name="Source Channel",
        items=vc_channel_items,
        description="Source vertex colour channel"
    )
    
    dst_vc_layer: bpy.props.EnumProperty(
        name="Destination Layer",
        items=vc_layer_items,
        description="Destination vertex colour layer"
    )
    
    dst_vc_channel: bpy.props.EnumProperty(
        name="Destination Channel",
        items=vc_channel_items,
        description="Destination vertex colour channel"
    )


class AlphaToolPanel(bpy.types.Panel):
    bl_idname = "PAINT_PT_alpha_tool"
    bl_label = "Vertex Alpha Tool"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Alpha Tool'
    bl_context = 'vertexpaint'
    
    def draw(self, context):
        layout = self.layout
        mesh = context.object.data
        settings = context.scene.alpha_tool_props_group
        
        box_a = layout.box()
        box_a.label(text="Get vertex colours at selected vertex")
        box_a.operator("paint.get_colour_op", text="Get Colours")
        box_a.prop(settings, "vertex_colours")
        
        box_b = layout.box()
        box_b.label(text="Paste current colour without affecting alpha")
        box_b.operator("paint.paste_colour_op", text="Paste RGB")
        
        box_c = layout.box()
        box_c.label(text="Paste alpha")
        box_c.prop(settings, "alpha_constant")
        box_c.operator("paint.paste_alpha_op", text="Paste Alpha")
        
        box_d = layout.box()
        box_d.label(text="Copy + Paste vertex colour channel")
        row_src = box_d.row()
        row_src.prop(settings, "src_vc_layer")
        row_src.prop(settings, "src_vc_channel")
        row_dst = box_d.row()
        row_dst.prop(settings, "dst_vc_layer")
        row_dst.prop(settings, "dst_vc_channel")
        box_d.operator("paint.copy_paste_channel_op",
            text="Copy + Paste Channel")

class AlphaToolBaseOp(bpy.types.Operator):
    bl_idname = "paint.alpha_tool_base_op"
    bl_label = "Alpha Tool Operator"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        obj = bpy.context.object
        return obj and obj.mode == 'VERTEX_PAINT' and obj.type == 'MESH'


class GetColourOp(AlphaToolBaseOp):
    bl_idname = "paint.get_colour_op"
    
    def execute(self, context):
        selected_indexes = getSelVertIndexes()
        
        if selected_indexes.size != 1:
            context.scene.alpha_tool_props_group.vertex_colours = "Select exactly one vertex"
        else:
            vectors = getSelVertColour( getSelVertIndexes()[0] )
            
            colours = []
            
            for vector in vectors:
                value = 0
                for rgba in range(4):
                    value += (scaleColourValue(vector[rgba]) << ((3 - rgba) * 8))
                colours.append("{:08X}".format(value))
            
            context.scene.alpha_tool_props_group.vertex_colours = ' '.join(colours)
        
        return {'FINISHED'}


class PasteColourOp(AlphaToolBaseOp):
    bl_idname = "paint.paste_colour_op"
    
    def execute(self, context):
        
        r, g, b = context.tool_settings.vertex_paint.brush.color
        
        if context.object.data.use_paint_mask:
            self.report({'ERROR'}, "Masking by polygons not yet supported")
        elif context.object.data.use_paint_mask_vertex:
            selected_indexes = getSelVertIndexes()
            if selected_indexes.size:
                setVertsColours(selected_indexes, [(0, r), (1, g), (2, b)])
            else:
                self.report({'ERROR'}, "No vertices are selected")
                
        else:
            for mesh_loop_color in context.object.data.vertex_colors.active.data:
                mesh_loop_color.color[0] = r
                mesh_loop_color.color[1] = g
                mesh_loop_color.color[2] = b
        
        return {'FINISHED'}


class PasteAlphaOp(AlphaToolBaseOp):
    bl_idname = "paint.paste_alpha_op"
    
    def execute(self, context):
        
        a = context.scene.alpha_tool_props_group.alpha_constant
        
        if context.object.data.use_paint_mask:
            self.report({'ERROR'}, "Masking by polygons not yet supported")
        elif context.object.data.use_paint_mask_vertex:
            selected_indexes = getSelVertIndexes()
            if selected_indexes.size:
                setVertsColours(selected_indexes, [(3, a)])
            else:
                self.report({'ERROR'}, "No vertices are selected")
        else:
            for mesh_loop_color in context.object.data.vertex_colors.active.data:
                mesh_loop_color.color[3] = a
        
        return {'FINISHED'}


class CopyPasteChannelOp(AlphaToolBaseOp):
    bl_idname = "paint.copy_paste_channel_op"
    
    def execute(self, context):
        settings = context.scene.alpha_tool_props_group
               
        vc_layers = context.object.data.vertex_colors
        if (settings.src_vc_layer not in vc_layers or
            settings.dst_vc_layer not in vc_layers):
            self.report({'ERROR'}, ("Mesh does not have at least one of the "
                "selected vertex colour layers"))
        
        elif (settings.src_vc_layer == settings.dst_vc_layer and
            settings.src_vc_channel == settings.dst_vc_channel):
            self.report({'ERROR'}, "Destination is equal to source")
        
        else:
            rgba_map = {"r": 0, "g": 1, "b": 2, "a": 3}
            src_ind = rgba_map[settings.src_vc_channel]
            dst_ind = rgba_map[settings.dst_vc_channel]
            
            mesh = context.object.data
            bm = bmesh.new()
            bm.from_mesh(mesh)
            bm.verts.ensure_lookup_table()
            
            src_layer = bm.loops.layers.color[settings.src_vc_layer]
            dst_layer = bm.loops.layers.color[settings.dst_vc_layer]
            
            for i in range(0, len(bm.verts)):
                for loop in bm.verts[i].link_loops:
                    loop[dst_layer][dst_ind] = loop[src_layer][src_ind]

            bm.to_mesh(mesh)
            bm.free()
            
#            bpy.ops.object.mode_set(mode='OBJECT')
#            bpy.ops.object.mode_set(mode='VERTEX_PAINT')
#            for i in range(0, len(vc_layers[settings.src_vc_layer].data)):
#                vc_layers[settings.dst_vc_layer].data[i].color[dst_ind] = \
#                    vc_layers[settings.src_vc_layer].data[i].color[src_ind]
        
        return {'FINISHED'}


def scaleColourValue(value : float) -> int:
    value *= 256
    if value >= 255.5:
        return 255
    elif value < 0:
        return 0
    else:
        return int(value)


def getSelVertIndexes() -> np.ndarray:
    """
    Returns indexes of selected vertices or polygons in active mesh.
    -   https://docs.blender.org/api/current/bpy.types.Mesh.html#bpy.types.Mesh
    -   https://blender.stackexchange.com/questions/173627/how-to-get-index-or-location-of-point-selected-in-edit-mode-using-python-api
    -   https://blender.stackexchange.com/questions/1412/efficient-way-to-get-selected-vertices-via-python-without-iterating-over-the-en
    """
    mode_initial = bpy.context.object.mode
    bpy.ops.object.mode_set(mode='OBJECT')
    
    mesh = bpy.context.object.data
    
    selected = np.zeros(len(mesh.vertices), dtype=bool)
    mesh.vertices.foreach_get('select', selected)
    
    bpy.ops.object.mode_set(mode=mode_initial)
    return np.where(selected)[0]


def getSelVertColour(vertex_index: int) -> List[Vector]:
    """
    Returns vertex colour of the vertex at the given index.
    -   https://docs.blender.org/api/current/bmesh.types.html?highlight=link%20loops#bmesh.types.BMLayerCollection
    -   https://blender.stackexchange.com/questions/49341/how-to-get-the-uv-corresponding-to-a-vertex-via-the-python-api/49344
    """
    mode_initial = bpy.context.object.mode
    bpy.ops.object.mode_set(mode='EDIT')
    
    mesh = bpy.context.edit_object.data
    bm = bmesh.from_edit_mesh(mesh)
    bm.verts.ensure_lookup_table() # Required before vertex lookup
    vc_layer = bm.loops.layers.color.active
    
    colours = []
    if vc_layer is None:
        colours.append(Vector.Fill(4))
    else:
        
        for loop in bm.verts[vertex_index].link_loops:
            colours.append(loop[vc_layer])
    
    bpy.ops.object.mode_set(mode=mode_initial)
    return colours


def setVertsColours(vertex_indexes: np.ndarray, rgba_values: list):
    
    mesh = bpy.context.object.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.verts.ensure_lookup_table()
    vc_layer = bm.loops.layers.color.active
    
    for index in vertex_indexes:
        for loop in bm.verts[index].link_loops:
            for value in rgba_values:
                loop[vc_layer][value[0]] = value[1]

    bm.to_mesh(mesh)
    bm.free()


classes = [AlphaToolPropsGroup, AlphaToolPanel, GetColourOp, PasteColourOp,
    PasteAlphaOp, CopyPasteChannelOp, AlphaToolBaseOp]

def register():
    # add operators
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # register properties
    bpy.types.Scene.alpha_tool_props_group = bpy.props.PointerProperty(
        type = AlphaToolPropsGroup)
        
def unregister():
    # remove operators
    for cls in classes:
        bpy.utils.unregister_class(cls)
    
    # unregister properties
    del bpy.types.Scene.alpha_tool_props_group

# allows running addon from text editor
if __name__ == "__main__":
    register()