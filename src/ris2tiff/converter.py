"""RIS (Reversa 3D scanner) to TIFF 32-bit grayscale converter.

RIS file format (reverse-engineered):
- Header: 88 bytes
  - Bytes 0-3: Magic "RIS\\0"
  - Bytes 4-5: Byte order "II" (little-endian)
  - Bytes 8-11: uint32, unknown (observed: 13)
  - Bytes 12-15: uint32, total data size in bytes (file_size - 156)
  - Bytes 16-51: Bounding box (3 corners, 3 floats each)
    Corner 1 (x_min, y_min, z): bytes 16-27
    Corner 2 (x_max, y_min, z): bytes 28-39
    Corner 3 (x_min, y_max, z): bytes 40-51
  - Bytes 64-67: float32, step/resolution
  - Bytes 80-83: float32, range
  - Bytes 84-87: float32, offset
- Data: float32 little-endian, row-major, starting at offset 88
  - Default row width: 5201
  - Number of rows: total_floats // width
  - Null marker: -3.37e+38
  - Native units: millimeters (pixel pitch ~0.1mm, Z in mm)
- No footer (data extends to end of file)

Output convention:
- TIFF: Z values in meters
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


def read_ris(filepath: Path, width: int = RIS_DEFAULT_WIDTH) -> tuple[np.ndarray, dict]:
    """Read RIS file and return float32 height map + header metadata.

    Args:
        filepath: Path to the RIS file.
        width: Row width in pixels. Default 5201 (Reversa standard).

    Returns:
        Tuple of (2D numpy array float32, header metadata dict).
        Z values are converted to meters. Null marker is preserved.
    """
    filepath = Path(filepath)
    meta = parse_ris_header(filepath)

    with open(filepath, "rb") as f:
        f.seek(RIS_HEADER_SIZE)
        data = np.fromfile(f, dtype=np.float32)

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
    width: int = RIS_DEFAULT_WIDTH,
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
        default=RIS_DEFAULT_WIDTH,
        help=f"Row width in pixels (default: {RIS_DEFAULT_WIDTH})",
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
