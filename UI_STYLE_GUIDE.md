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
| Luna Visia | `ui/assets/lunavisia_logo.png` | PNG, 8-bit RGBA | 1254 x 1254 px | 616,506 bytes | 5.75rem x 4.5rem | 4rem x 3.4rem |

Logos render with `object-fit: contain` so their square source images keep
their aspect ratio within the header bounds.

## Luna Visia header-position invariant

The Luna Visia desktop header has a deliberately fixed vertical position. In
`ui/styles.py`, keep the main container at:

```css
.block-container {
    max-width: 1180px;
    padding-top: 2.35rem;
    padding-bottom: 3rem;
}
```

The mobile override remains `padding: 0.85rem 0.8rem 2rem` below `700px`.
Do not adjust either value indirectly with spacer elements, empty Markdown,
negative margins, transforms, or invisible components.

### Why this matters

Streamlit components create layout wrappers even when their iframe height is
zero. A hidden `component_html` popover-dismiss script was previously rendered
before the Visia header and repeatedly pushed the logo, title, and controls
down. Removing that component made the real header position deterministic; the
explicit `2.35rem` desktop padding then aligned it with the intended Luna
layout.

### Rules for future changes

- Before `LunaStyle.header()` runs, inject CSS only with `st.html(...)`, which
  does not create a visible layout block.
- Never place `st.container`, `st.markdown`, `st.empty`, `component_html`, or
  another layout-producing element before the header.
- If JavaScript behavior is required, do not mount it ahead of the header.
  Place it after the visible page content or implement it without a Streamlit
  layout wrapper.
- Preserve `.lv-header` at `min-height: 4.5rem`, the desktop logo at
  `5.75rem × 4.5rem`, and vertical centering on the containing horizontal block.
- Do not compensate for a new regression by repeatedly changing margins or
  padding. First inspect the render path for an unexpected element before the
  header.
- After changing header or global styling, verify both the source and the live
  container copy. Compose Watch must be running for automatic propagation;
  otherwise rebuild/recreate only the Visia UI container before visual review.

### Regression checklist

1. The logo and title begin at the established desktop height.
2. The logo, title, subtitle, and header controls remain vertically centered.
3. No empty element or iframe appears above the header in the Streamlit layout.
4. Mobile keeps the logo and title on one line and uses the mobile padding.
5. A hard refresh produces the same position as a normal Streamlit rerun.
