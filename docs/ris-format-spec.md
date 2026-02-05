# RIS file format specification

Reverse-engineered format for Reversa 3D scanner (Factum). All values little-endian.

## File layout

| Section | Offset | Size | Description |
|---------|--------|------|-------------|
| Header | 0 | 88 bytes | Metadata, bounding box, scan parameters |
| Data | 88 | w × h × 4 bytes | float32 height values (mm) |
| Footer | EOF - 68 | 68 bytes | Dimensions, validation fields |

Total size: `88 + (width × height × 4) + 68` bytes.

## Header (88 bytes)

| Offset | Type | Field | Example | Notes |
|--------|------|-------|---------|-------|
| 0–3 | char[4] | magic | `RIS\0` | File signature |
| 4–5 | char[2] | byte_order | `II` | Little-endian |
| 6–7 | uint16 | unknown | 2304 | Observed: 0x0009 |
| 8–11 | uint32 | unknown | 13 | Constant across files |
| 12–15 | uint32 | data_size | 114,549,316 | w × h × 4 (matches footer) |
| 16–27 | float32[3] | corner_1 | (x_min, y_min, z) | Bounding box, mm |
| 28–39 | float32[3] | corner_2 | (x_max, y_min, z) | Bounding box, mm |
| 40–51 | float32[3] | corner_3 | (x_min, y_max, z) | Bounding box, mm |
| 52–63 | — | reserved | 0 | 12 bytes, zeros |
| 64–67 | float32 | step | 10.0 | Resolution (mm) |
| 68–79 | — | reserved | 0 | 12 bytes, zeros |
| 80–83 | float32 | range | 9.999 | Scan range |
| 84–87 | float32 | offset | -0.163 | Z offset |

## Data

- Starts at offset 88
- Row-major float32 array
- Native units: millimeters
- Null marker: `-3.37e+38` (0xff7d87d7 as uint32)
- Actual rows may exceed footer-declared height by ~4 (scanner padding)

## Footer (68 bytes = 17 × uint32)

Located at last 68 bytes of file. Uses tag-value structure.

| Index | Field | Example (a1) | Example (a2) | Notes |
|-------|-------|--------------|--------------|-------|
| 0 | pixel_count | 28,610,901 | 21,849,401 | w × h |
| 1 | header_size | 88 | 88 | Constant |
| 2 | tag | 0x050fa2 | 0x050fa2 | Fixed ID |
| 3 | unknown | 26,406 | 25,206 | ≈ height × 6 |
| 4 | data_bytes | 114,443,604 | 87,397,604 | w × h × 4 |
| 5 | tag | 0x050fa3 | 0x050fa3 | Fixed ID |
| 6 | flag | 1 | 1 | |
| 7 | null_marker | 0xff7d87d7 | 0xff7d87d7 | -3.37e+38 |
| 8 | tag | 0x050fa7 | 0x050fa7 | Fixed ID |
| 9 | flag | 1 | 1 | |
| 10 | scale | 0x3f800000 | 0x3f800000 | 1.0 as float |
| 11 | tag | 0x040fa8 | 0x040fa8 | Fixed ID |
| 12 | flag | 1 | 1 | |
| 13 | **height** | **4,401** | **4,201** | **Image height (px)** |
| 14 | tag | 0x040fa9 | 0x040fa9 | Fixed ID |
| 15 | flag | 1 | 1 | |
| 16 | **width** | **6,501** | **5,201** | **Image width (px)** |

## Validation

- `magic == "RIS\0"`
- `footer[1] == 88` (header size)
- `footer[0] == footer[13] × footer[16]` (pixel_count = h × w)

## Output convention (ris2tiff)

- TIFF: Z in meters (mm ÷ 1000)
- TFW: pixel size 0.0001 m (0.1 mm)
- Bounding box converted to meters

---

*February 2026 — J. Cano, Factum Foundation*
