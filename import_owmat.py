import os
from . import bpyhelper
from . import read_owmat
from . import owm_types
import struct
import bpy

def cleanUnusedMaterials(materials):
    if materials is None:
        return
    m = {}
    for name in materials[1]:
        mat = materials[1][name]
        if mat.users == 0:
            print('[import_owmat]: removed material: {}'.format(mat.name))
            bpy.data.materials.remove(mat)
        else:
            m[name] = mat
    bpyhelper.scene_update()
    t = {}
    for name in materials[0]:
        tex = materials[0][name]
        if tex.users == 0:
            bpy.data.textures.remove(tex)
        else:
            t[name] = tex
    bpyhelper.scene_update()
    return (t, m)

def mutate_texture_path(file, new_ext):
    return os.path.splitext(file)[0] + new_ext

def load_textures(texture, root, t):
    ''' Loads an overwatch texture.'''
    realpath = bpyhelper.normpath(texture)
    if not os.path.isabs(realpath):
        realpath = bpyhelper.normpath('%s/%s' % (root, realpath))
    
    ''' If the specified file doesn't exist, try the dds variant '''
    dds_file = mutate_texture_path(realpath, '.dds')
    if not os.path.exists(realpath) and os.path.exists(dds_file):
        realpath = dds_file

    fn = os.path.splitext(os.path.basename(realpath))[0]
    
    try:
        tex = None
        if fn in t:
            tex = t[fn]
        else:
            img = None
            for eimg in bpy.data.images:
                if eimg.name == fn or eimg.filepath == realpath:
                    img = eimg
            if img is None:
                img = bpy.data.images.load(realpath, check_existing=True)
                img.name = fn
            tex = None
            for etex in bpy.data.textures:
                if etex.name == fn:
                    tex = etex
            if tex == None:
                tex = bpy.data.textures.new(name = fn, type='IMAGE')
                tex.image = img
            t[fn] = tex
        return tex
    except Exception as e:
        print('[import_owmat]: error loading texture: {}'.format(bpyhelper.format_exc(e)))
    return None

def read(filename, prefix = ''):
    root, file = os.path.split(filename)
    data = read_owmat.read(filename)
    if not data:
        return None

    t = {}
    m = {}

    for i in range(len(data.materials)):
        m[data.materials[i].key] = process_material(data.materials[i], prefix, root, t)

    return (t, m)

def process_material(material, prefix, root, t):
    mat = bpy.data.materials.new(name = '%s%016X' % (prefix, material.key))

    # print('Processing material: ' + mat.name)
    mat.use_nodes = True
   
    tile_x = 400
    tile_y = 300
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
       
    # Remove default nodes
    for node in [node for node in nodes if node.type != 'OUTPUT_MATERIAL']:
        nodes.remove(node)
 
    # Get material output node
    material_output = None
    try:
        material_output = [node for node in nodes if node.type == 'OUTPUT_MATERIAL'][0]
    except:
        material_output = nodes.new('ShaderNodeOutputMaterial')
    material_output.location = (tile_x, 0)
 
    # Create Overwatch NodeGroup Instance
    nodeOverwatch = nodes.new('ShaderNodeGroup')
    if material.shader != 0:
        # print('[import_owmat]: {} uses shader {}'.format(mat.name, material.shader))
        nodeOverwatch.label = 'OWM Shader %d' % (material.shader)
    
    if str(material.shader) in owm_types.TextureTypes['NodeGroups'] and owm_types.TextureTypes['NodeGroups'][str(material.shader)] in bpy.data.node_groups:
        nodeOverwatch.node_tree = bpy.data.node_groups[owm_types.TextureTypes['NodeGroups'][str(material.shader)]]
    else:
        if owm_types.TextureTypes['NodeGroups']['Default'] in bpy.data.node_groups:
            nodeOverwatch.node_tree = bpy.data.node_groups[owm_types.TextureTypes['NodeGroups']['Default']]
    nodeOverwatch.location = (0, 0)
    nodeOverwatch.width = 300
    if nodeOverwatch.node_tree is not None:
        links.new(nodeOverwatch.outputs[0], material_output.inputs[0])

    tt = owm_types.TextureTypesById
    tm = owm_types.TextureTypes

    nodeMapping = None
    uvNodes = {}
    for inputId in tm['Scale']:
        if inputId in material.static_inputs and len(material.static_inputs[inputId]) >= 8:
            scale_data = struct.unpack('<ff', material.static_inputs[inputId][0:8])
            scale_x = scale_data[0]
            scale_y = scale_data[1]
            if scale_x < 0.01: scale_x = 1
            if scale_y < 0.01: scale_y = 1
            nodeMapping = nodes.new('ShaderNodeMapping')
            nodeMapping.vector_type = 'TEXTURE'
            nodeMapping.location = (-(tile_x * 3), -(tile_y))

            nodeMapping.inputs[3].default_value[0] = scale_x
            nodeMapping.inputs[3].default_value[1] = scale_y

            nodeUV1 = nodes.new('ShaderNodeUVMap')
            nodeUV1.location = (-(tile_x * 4), -(tile_y))
            nodeUV1.uv_map = "UVMap1"
            links.new(nodeUV1.outputs[0], nodeMapping.inputs[0])
            uvNodes[1] = nodeMapping
            break

    scratchSocket = {}
    for i, texData in enumerate(material.textures):
        nodeTex = nodes.new('ShaderNodeTexImage')
        nodeTex.location = (-tile_x, -(tile_y * i))
        nodeTex.width = 250
        
        tex = load_textures(texData[0], root, t)
        if tex is None:
            print('[import_owmat]: failed to load texture: {}'.format(texData[0]))
            continue
        nodeTex.image = tex.image
        if nodeTex.image:
            nodeTex.image.colorspace_settings.name = 'Raw'
            nodeTex.image.alpha_mode = 'CHANNEL_PACKED'

        if len(texData) == 2:
            continue

        if nodeOverwatch.node_tree is None:
            continue

        typ = texData[2]
        nodeTex['owm.material.typeid'] = str(typ)
        nodeTex.label = str(typ)
        if typ in tt:
            bfTyp = tm['Mapping'][tt[typ]]
            # print('[import_owmat]: {} is {}'.format(os.path.basename(texData[0]), tt[typ]))
            nodeTex.label = str(tt[typ])
            nodeTex.name = str(tt[typ])
            for colorSocketPoint in bfTyp[0]:
                nodeSocketName = colorSocketPoint
                if colorSocketPoint in tm['Alias']:
                    nodeSocketName = tm['Alias'][colorSocketPoint]
                if colorSocketPoint not in scratchSocket:
                    if nodeSocketName in nodeOverwatch.inputs:
                        links.new(nodeTex.outputs['Color'], nodeOverwatch.inputs[nodeSocketName])
                        scratchSocket[colorSocketPoint] = nodeTex.outputs['Color']
            for alphaSocketPoint in bfTyp[1]:
                nodeSocketName = alphaSocketPoint
                if alphaSocketPoint in tm['Alias']:
                    nodeSocketName = tm['Alias'][alphaSocketPoint]
                if alphaSocketPoint not in scratchSocket:
                    if nodeSocketName in nodeOverwatch.inputs:
                        links.new(nodeTex.outputs['Alpha'], nodeOverwatch.inputs[nodeSocketName])
                        scratchSocket[alphaSocketPoint] = nodeTex.outputs['Alpha']
            uvMap = bfTyp[3] if len(bfTyp) > 3 else 0
            if uvMap != 0:
                if uvMap < 0:
                    static_input_hashes = bfTyp[4]
                    static_input_offsets = bfTyp[5]
                    static_input_mods = bfTyp[6]
                    uvMap = abs(uvMap)
                    for static_input_hash, hash_index in enumerate(static_input_hashes):
                        if static_input_hash in material.static_inputs:
                            input_chunk = material.static_inputs[static_input_hash][static_input_offsets[hash_index]:]
                            if len(input_chunk) > 1:
                                uvMap = int(input_chunk[0])
                                uvMap += static_input_mods[hash_index]
                            break
                nodeUV = None
                if uvMap in uvNodes:
                    nodeUV = uvNodes[uvMap]
                else:
                    nodeUV = nodes.new('ShaderNodeUVMap')
                    nodeUV.location = (-(tile_x * 2), -(tile_y * i))
                    nodeUV.uv_map = "UVMap%d" % (uvMap)
                    uvNodes[uvMap] = nodeUV
                links.new(nodeUV.outputs[0], nodeTex.inputs[0])
            elif nodeMapping != None:
                links.new(nodeMapping.outputs[0], nodeTex.inputs[0])

    if nodeOverwatch.node_tree is None:
        return mat
            
    for envPoint, basePoint in tm['Env'].items():
        if envPoint in scratchSocket or basePoint not in scratchSocket: continue
        nodeSocketName = envPoint
        if envPoint in tm['Alias']:
            nodeSocketName = tm['Alias'][envPoint]
        if nodeSocketName in nodeOverwatch.inputs:
            links.new(scratchSocket[basePoint], nodeOverwatch.inputs[nodeSocketName])
            scratchSocket[envPoint] = scratchSocket[basePoint]

    for activeNodePoint in tm['Active']:
        if activeNodePoint in scratchSocket:
            nodes.active = scratchSocket[activeNodePoint].node
            break

    for colorNodePoint in tm['Color']:
        if colorNodePoint in scratchSocket:
            if scratchSocket[colorNodePoint].node.image:
                scratchSocket[colorNodePoint].node.image.colorspace_settings.name = 'sRGB'

    mat.blend_method = 'HASHED'
    mat.shadow_method = 'HASHED'
    
    return mat
