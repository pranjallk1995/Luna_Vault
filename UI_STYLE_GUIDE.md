# Luna UI style guide

Shared visual reference for Luna Visia and Luna Vita.

## Color palette

| Role | Color |
| --- | --- |
| Background | `#111111` |
| Surface / panel | `rgba(255, 255, 255, 0.055)` |
| Control | `rgba(255, 255, 255, 0.07)` |
| Control hover | `rgba(255, 255, 255, 0.12)` |
| Primary text | `#f5f5f5` |
| Muted text | `#a3a3a3` |
| Border | `rgba(255, 255, 255, 0.14)` |
| Strong border | `rgba(255, 255, 255, 0.34)` |
| Accent | `#f5f5f5` |
| Accent surface | `rgba(255, 255, 255, 0.09)` |

The header subtitle uses the muted text color. Titles, selected controls, and
important foreground content use the primary text color.

## Typography scale

| Role | Size |
| --- | --- |
| App title | `clamp(1.65rem, 3vw, 2.15rem)` |
| Header subtitle | `0.78rem` (`--luna-text-subtitle`) |
| Body text | `0.88rem` |
| Supporting text / labels | `0.72rem` |

The shared font weights are `720` for the app title and `400` for the header
subtitle. Luna typography variables use the `--luna-text-*` prefix to avoid
collisions with framework theme variables.

## Logo assets

| App | Asset | Format | Resolution | File size | Desktop display | Mobile display |
| --- | --- | --- | --- | --- | --- | --- |
| Luna Vita | `ui/assets/lunavita_logo.png` | PNG, 8-bit RGBA | 1254 x 1254 px | 637,054 bytes | 5.75rem x 4.5rem | 4.25rem x 3.5rem |
| Luna Visia | `ui/assets/lunavisia_logo.png` | PNG, 8-bit RGBA | 1254 x 1254 px | 616,506 bytes | 5.75rem x 4.5rem | 4rem x 3.4rem |

Both logos render with `object-fit: contain` so their square source images keep
their aspect ratio within the header bounds.
