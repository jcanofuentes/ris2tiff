"""RIS (Reversa 3D scanner) to TIFF 32-bit grayscale converter.

RIS file format (reverse-engineered):

Header (88 bytes):
  - Bytes 0-3: Magic "RIS\\0"
  - Bytes 4-5: Byte order "II" (little-endian)
  - Bytes 6-7: uint16, unknown (observed: 0x0009 = 2304)
  - Bytes 8-11: uint32, unknown (observed: 13)
  - Bytes 12-15: uint32, data payload size in bytes (= width * height * 4)
  - Bytes 16-51: Bounding box (3 corners, 3 floats each, in mm)
    Corner 1 (x_min, y_min, z): bytes 16-27
    Corner 2 (x_max, y_min, z): bytes 28-39
    Corner 3 (x_min, y_max, z): bytes 40-51
  - Bytes 52-63: zeros (reserved)
  - Bytes 64-67: float32, step/resolution (mm)
  - Bytes 68-79: zeros (reserved)
  - Bytes 80-83: float32, range
  - Bytes 84-87: float32, offset

Data (starts at offset 88):
  - float32 little-endian, row-major
  - Null marker: -3.37e+38 (0xff7d87d7 as uint32)
  - Native units: millimeters (pixel pitch ~0.1mm, Z in mm)

Footer (68 bytes = 17 uint32, at end of file):
  The footer uses a tag-value structure. Tag IDs are stable across files;
  values vary per scan. Layout (0-based uint32 index from footer start):

  [0]  pixel_count     width * height
  [1]  header_size     88 (constant)
  [2]  tag 0x00050fa2  (331682)
  [3]  unknown         observed: height * 6
  [4]  data_bytes      width * height * 4 (matches header field at byte 12)
  [5]  tag 0x00050fa3  (331683)
  [6]  1               (count/flag)
  [7]  null_marker     0xff7d87d7 (-3.37e+38 as float32)
  [8]  tag 0x00050fa7  (331687)
  [9]  1               (count/flag)
  [10] scale_factor    0x3f800000 (1.0 as float32)
  [11] tag 0x00040fa8  (266152)
  [12] 1               (count/flag)
  [13] height          image height in pixels
  [14] tag 0x00040fa9  (266153)
  [15] 1               (count/flag)
  [16] width           image width in pixels

  Total file size = 88 (header) + width*height*4 (data) + 68 (footer).

Output convention:
- TIFF: Z values in meters (mm / 1000)
- TFW: pixel size 0.0001m (= 0.1mm), bounding box in meters
"""

import argparse
import struct
from pathlib import Path

import numpy as np
import tifffile
from PIL import Image

# RIS format constants
RIS_HEADER_SIZE = 88
RIS_FOOTER_SIZE = 68  # 17 uint32 values
RIS_DEFAULT_WIDTH = 5201
RIS_NULL_MARKER = -3.37e+38
MM_TO_M = 0.001
PIXEL_SIZE_M = 0.0001  # 0.1mm in meters


def parse_ris_header(filepath: Path) -> dict:
    """Parse RIS header and return metadata.

    Returns dict with keys: x_min, y_min, x_max, y_max (in mm),
    step, range, offset.
    """
    with open(filepath, "rb") as f:
        header = f.read(RIS_HEADER_SIZE)

    magic = header[:4]
    if magic != b"RIS\x00":
        raise ValueError(f"Not a RIS file (magic: {magic!r})")

    bbox = struct.unpack_from("<9f", header, 16)
    step = struct.unpack_from("<f", header, 64)[0]
    range_val = struct.unpack_from("<f", header, 80)[0]
    offset_val = struct.unpack_from("<f", header, 84)[0]

    return {
        "x_min": bbox[0],  # corner 1 x
        "y_min": bbox[1],  # corner 1 y
        "x_max": bbox[3],  # corner 2 x
        "y_max": bbox[7],  # corner 3 y
        "step": step,
        "range": range_val,
        "offset": offset_val,
    }


def parse_ris_footer(filepath: Path) -> dict:
    """Parse RIS footer (last 68 bytes) to extract width and height.

    Returns dict with keys: width, height, pixel_count.
    Raises ValueError if footer structure is not recognized.
    """
    filepath = Path(filepath)
    fsize = filepath.stat().st_size

    if fsize < RIS_HEADER_SIZE + RIS_FOOTER_SIZE:
        raise ValueError(f"File too small for RIS footer ({fsize} bytes)")

    with open(filepath, "rb") as f:
        f.seek(fsize - RIS_FOOTER_SIZE)
        footer = f.read(RIS_FOOTER_SIZE)

    vals = struct.unpack_from("<17I", footer, 0)

    # Validate known constants
    if vals[1] != RIS_HEADER_SIZE:
        raise ValueError(f"Footer header_size field is {vals[1]}, expected {RIS_HEADER_SIZE}")

    width = vals[16]
    height = vals[13]
    pixel_count = vals[0]

    if width * height != pixel_count:
        raise ValueError(
            f"Footer inconsistent: w={width} * h={height} = {width * height} != pixel_count={pixel_count}"
        )

    return {"width": width, "height": height, "pixel_count": pixel_count}


def read_ris(filepath: Path, width: int | None = None) -> tuple[np.ndarray, dict]:
    """Read RIS file and return float32 height map + header metadata.

    Args:
        filepath: Path to the RIS file.
        width: Row width in pixels. If None, auto-detected from footer.

    Returns:
        Tuple of (2D numpy array float32, header metadata dict).
        Z values are converted to meters. Null marker is preserved.
    """
    filepath = Path(filepath)
    meta = parse_ris_header(filepath)

    # Auto-detect width from footer if not specified
    if width is None:
        try:
            footer = parse_ris_footer(filepath)
            width = footer["width"]
            height = footer["height"]
            print(f"[INFO] Auto-detected from footer: {width} x {height}")
        except ValueError as e:
            width = RIS_DEFAULT_WIDTH
            print(f"[WARN] Footer parse failed ({e}), using default width {width}")

    # Read data payload (exclude 68-byte footer)
    fsize = filepath.stat().st_size
    data_bytes = fsize - RIS_HEADER_SIZE - RIS_FOOTER_SIZE
    data_floats = data_bytes // 4

    with open(filepath, "rb") as f:
        f.seek(RIS_HEADER_SIZE)
        data = np.fromfile(f, dtype=np.float32, count=data_floats)

    total_floats = len(data)
    rows = total_floats // width
    remainder = total_floats % width

    if remainder != 0:
        print(f"[WARN] {remainder} trailing floats discarded (not a full row)")

    grid = data[: rows * width].reshape((rows, width))

    # Convert Z from mm to meters, preserving null marker
    null_mask = grid <= RIS_NULL_MARKER
    grid = grid * MM_TO_M
    grid[null_mask] = RIS_NULL_MARKER

    print(f"[INFO] File: {filepath.name}")
    print(f"[INFO] Grid: {rows} x {width} ({total_floats} floats)")

    return grid, meta


def save_tiff(data: np.ndarray, filepath: Path) -> None:
    """Save array as TIFF 32-bit grayscale."""
    tifffile.imwrite(filepath, data.astype(np.float32), photometric="minisblack")


def save_tfw(tiff_path: Path, meta: dict, rows: int, cols: int) -> Path:
    """Write a TFW world file alongside the TIFF.

    Uses bounding box from RIS header (converted to meters).
    Pixel size: 0.0001m (0.1mm).
    Origin: upper-left pixel center.

    TFW format:
        Line 1: pixel size X (positive)
        Line 2: rotation Y (0)
        Line 3: rotation X (0)
        Line 4: pixel size Y (negative, image Y goes down)
        Line 5: X coordinate of upper-left pixel center
        Line 6: Y coordinate of upper-left pixel center
    """
    # Bounding box in meters
    x_min_m = meta["x_min"] * MM_TO_M
    y_max_m = meta["y_max"] * MM_TO_M  # upper-left Y

    # Upper-left pixel center
    x_origin = x_min_m + PIXEL_SIZE_M / 2
    y_origin = y_max_m - PIXEL_SIZE_M / 2

    tfw_path = tiff_path.with_suffix(".tfw")
    with open(tfw_path, "w") as f:
        f.write(f"{PIXEL_SIZE_M:.10f}\n")
        f.write("0.0000000000\n")
        f.write("0.0000000000\n")
        f.write(f"{-PIXEL_SIZE_M:.10f}\n")
        f.write(f"{x_origin:.10f}\n")
        f.write(f"{y_origin:.10f}\n")

    return tfw_path


def render_preview(
    data: np.ndarray,
    filepath: Path,
    azimuth: float = 315.0,
    elevation: float = 45.0,
    exaggeration: float = 1.0,
) -> Path:
    """Render a Lambertian-shaded preview of the height map and save as PNG.

    Args:
        data: 2D float32 height map (Z in meters). Null markers are masked.
        filepath: Output PNG path.
        azimuth: Light azimuth in degrees (0=N, 90=E, 180=S, 270=W).
        elevation: Light elevation in degrees above horizon (0-90).
        exaggeration: Z exaggeration factor for enhancing relief visibility.

    Returns:
        Path to the saved PNG.
    """
    # Mask null pixels, replace with NaN for gradient computation
    valid_mask = data > RIS_NULL_MARKER
    z = np.where(valid_mask, data * exaggeration, 0.0)

    # Compute normals from depth (gradient in real-world units: m/m = slope)
    gy, gx = np.gradient(z, PIXEL_SIZE_M)
    normals = np.stack((-gx, -gy, np.ones_like(z)), axis=-1)
    normals /= np.linalg.norm(normals, axis=-1, keepdims=True)

    # Light direction vector (azimuth-90 convention)
    el_rad, az_rad = np.radians([elevation, azimuth - 90])
    light = np.array([
        np.cos(el_rad) * np.sin(az_rad),
        np.cos(el_rad) * np.cos(az_rad),
        np.sin(el_rad),
    ])

    # Lambertian shading with fill light for back-facing surfaces
    shade = np.einsum("ijk,k->ij", normals, light)
    shade = np.where(shade < 0, 0.7 * np.abs(shade), shade)

    # Normalize to 0-255, null pixels -> 0
    shade = np.where(valid_mask, shade, 0.0)
    shade = np.nan_to_num(shade, nan=0.0)
    s_min, s_max = shade[valid_mask].min(), shade[valid_mask].max()
    if s_max > s_min:
        shade = (shade - s_min) / (s_max - s_min)
    img = (shade * 255).astype(np.uint8)
    img[~valid_mask] = 0

    Image.fromarray(img, mode="L").save(filepath)
    print(f"[OK] Preview: {filepath.name}")
    return filepath


def convert_ris_to_tiff(
    input_path: Path,
    output_path: Path | None = None,
    width: int | None = None,
    rotate: int = 0,
    azimuth: float = 315.0,
    elevation: float = 45.0,
    exaggeration: float = 1.0,
) -> Path:
    """Convert RIS file to TIFF 32-bit grayscale + TFW world file.

    Z values are converted from mm to meters.
    A .tfw world file is generated with pixel size 0.0001m.

    Args:
        input_path: Path to input RIS file.
        output_path: Path for output TIFF. Defaults to same name with .tif.
        width: Row width in pixels.
        rotate: Counterclockwise rotation in degrees (must be multiple of 90).

    Returns:
        Path to the output TIFF file.
    """
    input_path = Path(input_path)

    if output_path is None:
        output_path = input_path.with_suffix(".tif")
    else:
        output_path = Path(output_path)

    data, meta = read_ris(input_path, width=width)

    # Optional rotation (counterclockwise, in 90° steps)
    if rotate != 0:
        k = rotate // 90
        data = np.rot90(data, k=k)
        print(f"[INFO] Rotated {rotate} degrees CCW ({data.shape[0]} x {data.shape[1]})")

    save_tiff(data, output_path)

    rows, cols = data.shape
    tfw_path = save_tfw(output_path, meta, rows, cols)

    # Stats excluding null marker (Z already in meters)
    valid = data[data > RIS_NULL_MARKER]
    if len(valid) > 0:
        print(f"[INFO] Z range (m): [{valid.min():.6f}, {valid.max():.6f}]")
    null_count = np.sum(data <= RIS_NULL_MARKER)
    if null_count > 0:
        print(f"[INFO] Null pixels: {null_count}")

    print(f"[OK] {input_path.name} -> {output_path.name}")
    print(f"[OK] World file: {tfw_path.name}")

    # Render Lambertian preview
    preview_path = output_path.with_name(output_path.stem + "_preview.png")
    render_preview(data, preview_path, azimuth=azimuth, elevation=elevation, exaggeration=exaggeration)

    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Convert RIS (Reversa 3D scanner) to TIFF 32-bit grayscale"
    )
    parser.add_argument("input", type=Path, help="Input RIS file")
    parser.add_argument(
        "-o", "--output", type=Path, help="Output TIFF file (default: same name .tif)"
    )
    parser.add_argument(
        "-w",
        "--width",
        type=int,
        default=None,
        help=f"Row width in pixels (default: auto-detect from footer)",
    )
    parser.add_argument(
        "-r",
        "--rotate",
        type=int,
        default=0,
        choices=[0, 90, 180, 270],
        help="Counterclockwise rotation in degrees (default: 0)",
    )
    parser.add_argument(
        "--azimuth",
        type=float,
        default=315.0,
        help="Light azimuth in degrees for preview (default: 315)",
    )
    parser.add_argument(
        "--elevation",
        type=float,
        default=45.0,
        help="Light elevation in degrees for preview (default: 45)",
    )
    parser.add_argument(
        "--exaggeration",
        type=float,
        default=1.0,
        help="Z exaggeration factor for preview (default: 1.0)",
    )

    args = parser.parse_args()
    convert_ris_to_tiff(
        args.input, args.output,
        width=args.width, rotate=args.rotate,
        azimuth=args.azimuth, elevation=args.elevation,
        exaggeration=args.exaggeration,
    )


if __name__ == "__main__":
    main()
