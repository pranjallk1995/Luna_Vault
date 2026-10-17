# Luna UI style guide

Shared visual reference for Luna Visia, Luna Vita, and Luna Lumia.

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

- Before `LunaVisiaApp.render_header()` runs, inject CSS only with `st.html(...)`, which
  does not create a visible layout block.
- Vita and Lumia must use the same `2.35rem` desktop container top padding as
  Visia. Keep Vita's header row intrinsic, matching Visia; forcing a fixed row
  height pushes its navigation down. Lumia's tabs do not have the segmented-
  control wrapper used by Visia, so their desktop tab-list top margin is
  `1.2rem` to preserve the same on-screen navigation baseline.
- Keep Vita's navigation in normal document flow. Do not apply `top`,
  `transform`, or negative-margin corrections to
  `.st-key-nutrition_navigation`; those corrections render the navbar too high
  in the user's browser even when a headless measurement suggests otherwise.
- Do not add invisible date, power, or navigation anchor elements inside the
  header columns; Streamlit still allocates vertical gap around their wrappers.
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

## Shared Luna app-shell contract

Luna Visia is the canonical visual reference for every Luna app. Luna Vita,
Luna Lumia, and future apps must use the same app-shell geometry and interaction
language. Product-specific content begins below the navbar; the shell above it
must not be redesigned per app.

### Required shell structure

Every desktop app renders these elements in this order:

1. A two-column header created with `st.columns([5, 4],
   vertical_alignment="center", gap="medium")`.
2. The left column contains one `.lv-header` with the app logo, title, and
   subtitle.
3. The right column contains the app's main control: Visia's upload/view
   console, Vita's date control, Lumia's all-lights power control, or the
   equivalent primary console in a future app.
4. The full-width primary navbar immediately follows the header row.

Do not insert Markdown spacers, empty containers, hidden anchors, iframe
components, or status elements between these parts. Even invisible Streamlit
elements can add vertical layout gaps.

### Header and branding geometry

Use these desktop values unchanged:

```css
.block-container {
    max-width: 1180px;
    padding-top: 2.35rem;
    padding-bottom: 3rem;
}

div[data-testid="stHorizontalBlock"]:has(.lv-header) {
    align-items: center;
    margin-bottom: .55rem;
}

.lv-header {
    display: flex;
    align-items: center;
    gap: 1rem;
    min-height: 4.5rem;
    margin-bottom: 1rem;
}

.lv-mark {
    flex: 0 0 5.75rem;
    width: 5.75rem;
    height: 4.5rem;
    object-fit: contain;
}
```

The app title uses `--luna-text-title`, weight `720`, letter spacing `-.04em`,
and line height `1`. The subtitle uses `--luna-text-subtitle` (`.78rem`), weight
`400`, and the muted color. Logo, title, subtitle, and the right-side console
must remain vertically centered as a single header row.

### Right-side main console

The right-side control occupies the complete second header column. A single
button, date field, or console surface must stretch to the column width and use
a minimum height of `2.625rem`. Use the shared control background, strong border
for emphasis, `.65rem` control radius, and the same Luna typography as the
navbar. Do not position this console with manual offsets or independent spacer
elements.

On mobile, both header columns become full width. The brand stays on one line;
the main console moves below it and remains full width.

### Navbar location and geometry

The navbar must begin at the same rendered Y coordinate as Luna Visia at the
same viewport size, browser zoom, and root font size. It is full container
width and uses equal-width items. The canonical surface is:

```css
gap: .2rem;
margin: .2rem 0 1.15rem;
padding: .4rem;
border: 1px solid var(--lv-border);
border-radius: .9rem;
background: var(--lv-surface);
```

Each item has a minimum height of `2.55rem`, a `.65rem` radius, and no default
Streamlit box shadow. Use Material icons followed by the label. Tabs,
segmented controls, and buttons create different internal wrappers, so a future
app should reuse Visia's segmented-control structure where possible. If another
widget is required, normalize its wrapper spacing rather than moving the
navbar with `top`, `transform`, negative margins, or invisible anchors.

### Navbar typography and states

All navbar labels and Material icons use the same muted foreground color in
every state. Selection and hover must never make the label brighter or whiter.
Communicate state through the surface and border only.

- Default: control background, transparent item border, muted icon and label.
- Selected: hover/control surface, strong `1px` border, subtle shared border
  ring, muted icon and label.
- Hover: hover/control surface, strong border, and `translateY(-1px)` with a
  `140ms` border/background/transform transition; icon and label stay muted.
- Focus: retain an accessible visible outline without changing the text color.

Apply the muted color to the button/tab itself and all nested `p`, `span`,
Material-icon, and `svg` nodes with sufficient selector specificity. Streamlit
often applies its primary foreground color to nested nodes, so styling only the
outer control is not enough.

### Fourth-app implementation checklist

1. Copy the app-shell variables and structural CSS from Visia before building
   product-specific pages.
2. Use the same `[5, 4]` header columns, `.lv-header` markup, logo box, title,
   subtitle, and full-width right-side console.
3. Reuse Visia's full-width segmented navigation when technically possible;
   change only the labels, Material icons, state keys, and selected markers.
4. Keep shell CSS in one style module and render it with `st.html(...)` before
   the header, without creating a layout-producing wrapper.
5. Compare all Luna apps at the same viewport width and 100% zoom. Measure the
   navbar's bounding-box `top`, `left`, and `width`; all apps should agree to
   within one device pixel.
6. Verify default, selected, hover, keyboard-focus, normal rerun, hard refresh,
   and mobile states. Do not approve the shell from a static source review
   alone.
7. Record any deliberate shared-shell change here first, then apply and verify
   it across every Luna app together.
