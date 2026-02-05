# RIS file format: footer structure and automatic width detection

## Background

The `ris2tiff` converter transforms `.RIS` files from the Reversa scanner (Factum) to 32-bit TIFF with worldfile. Previously, row width was assumed constant (5201 px for 52 cm scanners) and required manual adjustment for other configurations.

When `B23-Throne_a1.RIS` failed to convert correctly with `w=5201`, analysis revealed the file uses `w=6501` — outside the expected range.

## Footer structure

RIS files contain a 68-byte footer (17 `uint32` little-endian) at the end of the file with embedded metadata including image dimensions.

**Key fields:**

| Index | Content | Notes |
|-------|---------|-------|
| 0 | pixel_count | width × height |
| 1 | header_size | 88 (constant) |
| 13 | **height** | image height in pixels |
| 16 | **width** | image width in pixels |

**File layout:** `header (88) + data (w × h × 4) + footer (68)` bytes.

Example values:

| File | width | height | pixel_count |
|------|-------|--------|-------------|
| B23-Throne_a1.RIS | 6501 | 4401 | 28,610,901 |
| B23-Throne_a2.RIS | 5201 | 4201 | 21,849,401 |

## Implementation

`parse_ris_footer()` reads the last 68 bytes and extracts width/height. `read_ris()` now auto-detects dimensions when `width=None` (default).

```python
def parse_ris_footer(filepath: Path) -> dict:
    # Read last 68 bytes, extract vals[16] as width, vals[13] as height
    ...

def read_ris(filepath: Path, width: int | None = None):
    if width is None:
        footer = parse_ris_footer(filepath)
        width = footer["width"]
    ...
```

CLI and GUI default to `auto`. Manual override still available via `--width`.

## Notes

- Actual data rows may exceed footer-declared height by ~4 rows (scanner padding)
- Footer validation: `width × height == pixel_count` and `header_size == 88`

---

*February 2026*
