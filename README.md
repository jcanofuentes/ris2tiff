# ris2tiff

Converter from RIS (Reversa 3D scanner) to TIFF 32-bit grayscale.

## Setup

```
uv sync
```

## Usage

```
uv run ris2tiff input.ris
uv run ris2tiff input.ris -o output.tif
uv run ris2tiff input.ris -w 4800          # custom row width
```

## RIS format (reverse-engineered)

- Header: 88 bytes (magic `RIS\0`, byte order `II`, bounding box, resolution)
- Data: float32 little-endian, row-major, from offset 88 to end of file
- Default row width: 5201
- Null marker: -3.37e+38
- Number of rows varies per file (derived from file size)
