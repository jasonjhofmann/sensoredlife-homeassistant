# Brand assets

Archival copies of the brand artwork. The canonical assets are in
`custom_components/sensoredlife/brand/`, which Home Assistant 2026.3 and later
serves through its Brands Proxy, so no home-assistant/brands pull request is
needed. That repository now closes submissions for custom integrations
automatically.

| File | Size | Notes |
| --- | --- | --- |
| `icon.png` / `icon@2x.png` | 256² / 512² | SensoredLife house + 7 dots, dark house, transparent |
| `dark_icon.png` / `dark_icon@2x.png` | 256² / 512² | Same, light house (#F4F4F4) for dark themes |
| `logo.png` / `logo@2x.png` | 456×256 / 912×512 | MarCELL wordmark, black |
| `dark_logo.png` / `dark_logo@2x.png` | 456×256 / 912×512 | MarCELL wordmark, light (#F4F4F4) for dark themes |

- **Icons** are the SensoredLife house-and-dots mark; since it's wider than tall,
  it's centered in the square with transparent top/bottom padding (the brands
  guide prefers fully-trimmed squares, but this keeps the real mark intact).
- **Logos** are the MarCELL 2022 wordmark (from `MarCELL-2022.svg`).
- Brand colors: dots `#23A0F4`, house/wordmark `#0F0F0F` (light variant `#F4F4F4`).

Full-res transparent masters (house+dots and MarCELL wordmark, both color
variants) live in the local "Sensored Life" work folder.
