import base64
import json
import math
import struct
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("/Users/abhay/Downloads/Frame 9 (1).png")
OUT = ROOT / "output" / "zodex_brain_logo_relief.glb"
OUT_COMPAT = ROOT / "output" / "zodex.glb"
PREVIEW_TEX = ROOT / "output" / "zodex_brain_logo_texture.png"


def pad4(data: bytes, pad_byte: bytes = b"\x00") -> bytes:
    return data + pad_byte * ((4 - len(data) % 4) % 4)


def add_buffer_view(binary_parts, data: bytes, target=None):
    offset = sum(len(part) for part in binary_parts)
    padded = pad4(data)
    binary_parts.append(padded)
    view = {"buffer": 0, "byteOffset": offset, "byteLength": len(data)}
    if target is not None:
        view["target"] = target
    return view


def make_texture(src: Image.Image) -> bytes:
    rgba = src.convert("RGBA")
    gray = rgba.convert("L")
    arr = np.asarray(rgba).astype(np.float32)
    lum = np.asarray(gray).astype(np.float32)

    # Keep the brain and type, remove the black square around it.
    alpha = np.clip((lum - 8.0) / 72.0, 0.0, 1.0) ** 0.85
    arr[..., 3] = alpha * 255.0

    out = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")
    out.save(PREVIEW_TEX)
    buf = BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()


def build_mesh(src: Image.Image, resolution=190):
    # Square relief mesh: bright pixels rise forward, dark areas stay nearly flat.
    small = src.convert("L").resize((resolution, resolution), Image.Resampling.LANCZOS)
    small = small.filter(ImageFilter.GaussianBlur(radius=0.55))
    lum = np.asarray(small).astype(np.float32) / 255.0

    x = np.linspace(-3.0, 3.0, resolution, dtype=np.float32)
    y = np.linspace(3.0, -3.0, resolution, dtype=np.float32)
    xx, yy = np.meshgrid(x, y)

    mask = np.clip((lum - 0.03) / 0.55, 0.0, 1.0)
    height = (mask ** 1.45) * 0.48

    positions = np.stack([xx, yy, height], axis=-1).reshape(-1, 3).astype(np.float32)

    # Texture coordinates match the original image orientation.
    u = np.linspace(0.0, 1.0, resolution, dtype=np.float32)
    v = np.linspace(1.0, 0.0, resolution, dtype=np.float32)
    uu, vv = np.meshgrid(u, v)
    texcoords = np.stack([uu, vv], axis=-1).reshape(-1, 2).astype(np.float32)

    # Normals from the height field.
    dy, dx = np.gradient(height, y, x)
    normals = np.dstack((-dx, -dy, np.ones_like(height)))
    normals /= np.linalg.norm(normals, axis=-1, keepdims=True)
    normals = normals.reshape(-1, 3).astype(np.float32)

    indices = []
    for row in range(resolution - 1):
        for col in range(resolution - 1):
            a = row * resolution + col
            b = a + 1
            c = a + resolution
            d = c + 1
            indices.extend([a, c, b, b, c, d])
    indices = np.asarray(indices, dtype=np.uint32)

    return positions, normals, texcoords, indices


def minmax(values):
    return values.min(axis=0).tolist(), values.max(axis=0).tolist()


def build_gltf_and_binary(resolution=190, embed_data_uri=False):
    src = Image.open(SOURCE)
    texture_png = make_texture(src)
    positions, normals, texcoords, indices = build_mesh(src, resolution=resolution)

    binary_parts = []
    views = []
    accessors = []

    pos_view = len(views)
    views.append(add_buffer_view(binary_parts, positions.tobytes(), 34962))
    mn, mx = minmax(positions)
    accessors.append(
        {
            "bufferView": pos_view,
            "componentType": 5126,
            "count": int(len(positions)),
            "type": "VEC3",
            "min": mn,
            "max": mx,
        }
    )

    normal_view = len(views)
    views.append(add_buffer_view(binary_parts, normals.tobytes(), 34962))
    accessors.append(
        {
            "bufferView": normal_view,
            "componentType": 5126,
            "count": int(len(normals)),
            "type": "VEC3",
        }
    )

    uv_view = len(views)
    views.append(add_buffer_view(binary_parts, texcoords.tobytes(), 34962))
    accessors.append(
        {
            "bufferView": uv_view,
            "componentType": 5126,
            "count": int(len(texcoords)),
            "type": "VEC2",
        }
    )

    index_view = len(views)
    views.append(add_buffer_view(binary_parts, indices.tobytes(), 34963))
    accessors.append(
        {
            "bufferView": index_view,
            "componentType": 5125,
            "count": int(len(indices)),
            "type": "SCALAR",
        }
    )

    image_view = len(views)
    views.append(add_buffer_view(binary_parts, texture_png))

    binary = b"".join(binary_parts)
    gltf = {
        "asset": {
            "version": "2.0",
            "generator": "Codex relief exporter for ZODEX logo",
            "copyright": "Generated from user-provided reference image",
        },
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [
            {
                "name": "ZODEX brain logo relief",
                "mesh": 0,
                "rotation": [math.sin(math.radians(0) / 2), 0, 0, math.cos(math.radians(0) / 2)],
            }
        ],
        "meshes": [
            {
                "name": "Transparent height-field relief from source artwork",
                "primitives": [
                    {
                        "attributes": {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2},
                        "indices": 3,
                        "material": 0,
                        "mode": 4,
                    }
                ],
            }
        ],
        "materials": [
            {
                "name": "White logo and brain texture",
                "pbrMetallicRoughness": {
                    "baseColorTexture": {"index": 0},
                    "baseColorFactor": [1, 1, 1, 1],
                    "metallicFactor": 0.0,
                    "roughnessFactor": 0.72,
                },
                "emissiveTexture": {"index": 0},
                "emissiveFactor": [0.22, 0.22, 0.22],
                "alphaMode": "BLEND",
                "doubleSided": True,
            }
        ],
        "textures": [{"source": 0, "sampler": 0}],
        "samplers": [{"magFilter": 9729, "minFilter": 9987, "wrapS": 33071, "wrapT": 33071}],
        "images": [{"name": "ZODEX transparent texture", "mimeType": "image/png", "bufferView": image_view}],
        "accessors": accessors,
        "bufferViews": views,
        "buffers": [{"byteLength": len(binary)}],
    }

    if embed_data_uri:
        gltf["buffers"][0]["uri"] = "data:application/octet-stream;base64," + base64.b64encode(binary).decode("ascii")

    return gltf, binary, len(positions), len(indices) // 3


def write_glb(path: Path, resolution=190, embed_data_uri=False):
    gltf, binary, vertex_count, triangle_count = build_gltf_and_binary(
        resolution=resolution,
        embed_data_uri=embed_data_uri,
    )

    json_chunk = pad4(json.dumps(gltf, separators=(",", ":")).encode("utf-8"), b" ")
    bin_chunk = b"" if embed_data_uri else pad4(binary)

    total_length = 12 + 8 + len(json_chunk)
    if bin_chunk:
        total_length += 8 + len(bin_chunk)
    header = struct.pack("<III", 0x46546C67, 2, total_length)
    json_header = struct.pack("<I4s", len(json_chunk), b"JSON")
    if bin_chunk:
        bin_header = struct.pack("<I4s", len(bin_chunk), b"BIN\x00")
        path.write_bytes(header + json_header + json_chunk + bin_header + bin_chunk)
    else:
        path.write_bytes(header + json_header + json_chunk)

    print(f"Wrote {path}")
    print(f"Texture preview {PREVIEW_TEX}")
    print(f"Vertices {vertex_count:,}, triangles {triangle_count:,}")


if __name__ == "__main__":
    write_glb(OUT, resolution=190, embed_data_uri=False)
    write_glb(OUT_COMPAT, resolution=150, embed_data_uri=True)
