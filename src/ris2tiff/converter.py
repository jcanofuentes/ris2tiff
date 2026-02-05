"""RIS (Reversa 3D scanner) to TIFF 32-bit grayscale converter.

RIS file format (reverse-engineered):
- Header: 88 bytes
  - Bytes 0-3: Magic "RIS\\0"
  - Bytes 4-5: Byte order "II" (little-endian)
  - Bytes 8-11: uint32, unknown (observed: 13)
  - Bytes 12-15: uint32, total data size in bytes (file_size - 156)
  - Bytes 16-51: Bounding box (3 corners, 3 floats each)
  - Bytes 64-67: float32, step/resolution
  - Bytes 80-83: float32, range
  - Bytes 84-87: float32, offset
- Data: float32 little-endian, row-major, starting at offset 88
  - Default row width: 5201
  - Number of rows: total_floats // width
  - Null marker: -3.37e+38
- No footer (data extends to end of file)
"""

import argparse
from pathlib import Path

import numpy as np
import tifffile

# RIS format constants
RIS_HEADER_SIZE = 88
RIS_DEFAULT_WIDTH = 5201
RIS_NULL_MARKER = -3.37e+38


def read_ris(filepath: Path, width: int = RIS_DEFAULT_WIDTH) -> np.ndarray:
    """Read RIS file and return float32 height map.

    Args:
        filepath: Path to the RIS file.
        width: Row width in pixels. Default 5201 (Reversa standard).

    Returns:
        2D numpy array (float32) with height values.
        Null data points are preserved as-is (-3.37e+38).
    """
    filepath = Path(filepath)
    file_size = filepath.stat().st_size

    with open(filepath, "rb") as f:
        # Validate magic
        magic = f.read(4)
        if magic != b"RIS\x00":
            raise ValueError(f"Not a RIS file (magic: {magic!r})")

        # Skip rest of header
        f.seek(RIS_HEADER_SIZE)

        # Read all float32 data to end of file
        data = np.fromfile(f, dtype=np.float32)

    total_floats = len(data)
    rows = total_floats // width
    remainder = total_floats % width

    if remainder != 0:
        print(f"[WARN] {remainder} trailing floats discarded (not a full row)")

    grid = data[: rows * width].reshape((rows, width))

    print(f"[INFO] File: {filepath.name}")
    print(f"[INFO] Grid: {rows} x {width} ({total_floats} floats)")

    return grid


def save_tiff(data: np.ndarray, filepath: Path) -> None:
    """Save array as TIFF 32-bit grayscale."""
    tifffile.imwrite(filepath, data.astype(np.float32), photometric="minisblack")


def convert_ris_to_tiff(
    input_path: Path,
    output_path: Path | None = None,
    width: int = RIS_DEFAULT_WIDTH,
) -> Path:
    """Convert RIS file to TIFF 32-bit grayscale.

    Args:
        input_path: Path to input RIS file.
        output_path: Path for output TIFF. Defaults to same name with .tif.
        width: Row width in pixels.

    Returns:
        Path to the output TIFF file.
    """
    input_path = Path(input_path)

    if output_path is None:
        output_path = input_path.with_suffix(".tif")
    else:
        output_path = Path(output_path)

    data = read_ris(input_path, width=width)
    save_tiff(data, output_path)

    # Stats excluding null marker
    valid = data[data > RIS_NULL_MARKER]
    if len(valid) > 0:
        print(f"[INFO] Range: [{valid.min():.4f}, {valid.max():.4f}]")
    null_count = np.sum(data <= RIS_NULL_MARKER)
    if null_count > 0:
        print(f"[INFO] Null pixels: {null_count}")

    print(f"[OK] {input_path.name} -> {output_path.name}")

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

    args = parser.parse_args()
    convert_ris_to_tiff(args.input, args.output, width=args.width)


if __name__ == "__main__":
    main()
