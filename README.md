# ris2tiff

Converter from RIS (Reversa 3D scanner) to TIFF 32-bit grayscale with worldfile.

## Setup

```
uv sync
```

## Usage

```
uv run ris2tiff input.ris                  # auto-detect dimensions
uv run ris2tiff input.ris -o output.tif
uv run ris2tiff input.ris -w 5201          # manual width override
uv run ris2tiff-gui                        # GUI mode
```

## RIS format

File layout: `header (88 bytes) + data (w×h×4) + footer (68 bytes)`

### Header (88 bytes)

| Offset | Type | Field |
|--------|------|-------|
| 0–3 | char[4] | Magic `RIS\0` |
| 4–5 | char[2] | Byte order `II` (little-endian) |
| 12–15 | uint32 | Data size (w × h × 4) |
| 16–51 | float32[9] | Bounding box corners (mm) |
| 64–67 | float32 | Step/resolution (mm) |
| 80–83 | float32 | Range |
| 84–87 | float32 | Offset |

### Data

- float32 little-endian, row-major
- Units: millimeters
- Null marker: `-3.37e+38`

### Footer (68 bytes)

| Index | Field |
|-------|-------|
| 0 | Pixel count (w × h) |
| 1 | Header size (88) |
| 13 | **Height** (px) |
| 16 | **Width** (px) |

See [docs/ris-format-spec.md](docs/ris-format-spec.md) for full specification.

## Output

- TIFF 32-bit grayscale (Z in meters)
- TFW worldfile (pixel size 0.0001 m)
- PNG Lambert-shaded preview
