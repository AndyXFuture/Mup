---
name: Extruded Light
colors:
  surface: '#f7f9ff'
  surface-dim: '#d8dae0'
  surface-bright: '#f7f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f2f3f9'
  surface-container: '#eceef4'
  surface-container-high: '#e6e8ee'
  surface-container-highest: '#e0e2e8'
  on-surface: '#181c20'
  on-surface-variant: '#464554'
  inverse-surface: '#2d3135'
  inverse-on-surface: '#eff1f7'
  outline: '#767586'
  outline-variant: '#c7c4d7'
  surface-tint: '#494bd6'
  primary: '#4648d4'
  on-primary: '#ffffff'
  primary-container: '#6063ee'
  on-primary-container: '#fffbff'
  inverse-primary: '#c0c1ff'
  secondary: '#5b5f64'
  on-secondary: '#ffffff'
  secondary-container: '#dde0e5'
  on-secondary-container: '#606368'
  tertiary: '#8039b0'
  on-tertiary: '#ffffff'
  tertiary-container: '#9b54cb'
  on-tertiary-container: '#fffbff'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#e1e0ff'
  primary-fixed-dim: '#c0c1ff'
  on-primary-fixed: '#07006c'
  on-primary-fixed-variant: '#2f2ebe'
  secondary-fixed: '#e0e2e8'
  secondary-fixed-dim: '#c4c6cc'
  on-secondary-fixed: '#181c20'
  on-secondary-fixed-variant: '#44474c'
  tertiary-fixed: '#f3daff'
  tertiary-fixed-dim: '#e3b5ff'
  on-tertiary-fixed: '#2f004c'
  on-tertiary-fixed-variant: '#691f98'
  background: '#f7f9ff'
  on-background: '#181c20'
  surface-variant: '#e0e2e8'
typography:
  headline-xl:
    fontFamily: Plus Jakarta Sans
    fontSize: 40px
    fontWeight: '600'
    lineHeight: 48px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Plus Jakarta Sans
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.01em
  headline-lg-mobile:
    fontFamily: Plus Jakarta Sans
    fontSize: 28px
    fontWeight: '600'
    lineHeight: 36px
  headline-md:
    fontFamily: Plus Jakarta Sans
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  body-lg:
    fontFamily: Plus Jakarta Sans
    fontSize: 18px
    fontWeight: '500'
    lineHeight: 28px
  body-md:
    fontFamily: Plus Jakarta Sans
    fontSize: 16px
    fontWeight: '500'
    lineHeight: 24px
  label-md:
    fontFamily: Plus Jakarta Sans
    fontSize: 14px
    fontWeight: '600'
    lineHeight: 20px
    letterSpacing: 0.01em
  label-sm:
    fontFamily: Plus Jakarta Sans
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.02em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  base: 8px
  xs: 4px
  sm: 12px
  md: 24px
  lg: 48px
  xl: 80px
  gutter: 24px
  margin-mobile: 16px
  margin-desktop: 64px
---

## Brand & Style
The brand personality is tactile, serene, and sophisticated. It focuses on a "Soft UI" or Neomorphic aesthetic where the interface feels like a physical, molded surface rather than a flat screen. The target audience values premium digital craftsmanship and a sense of calm during interaction.

The design style is defined by **Neomorphism**. UI elements are not "placed on" the background; they are part of the background, either extruded outward or pressed inward. This creates a monochromatic, sculptural depth that relies on the precise play of light and shadow rather than high-contrast color blocks. The emotional response should be one of "digital haptics"—a desire to touch and interact with the soft, pillowy surfaces.

## Colors
The color palette is strictly anchored to the base "Clay" hue (#E8EAF0). For the Neomorphic effect to function, almost all UI surfaces must match this hex code exactly, as the depth is created by shadows and highlights of the same base color.

- **Primary (Indigo):** Reserved for high-intent interactive elements, active icons, and focus indicators. It should be used sparingly to maintain the soft aesthetic.
- **Tertiary (Violet):** Used for subtle highlights, success states, or secondary accentuation.
- **On Surface:** A deep charcoal-gray for high-readability text.
- **On Surface Variant:** A muted slate-gray for secondary information and labels.

## Typography
The typography system utilizes **Plus Jakarta Sans** to complement the rounded, soft nature of the UI. To maintain the "Soft UI" look, avoid Bold (700+) weights, which can feel too aggressive against the delicate shadows. Instead, use SemiBold (600) for hierarchy in headings and Medium (500) for body text.

The type scale is generous. Headings use slightly tighter letter spacing to feel more cohesive as "objects" on the screen. Body text remains open and legible. All text should maintain high contrast against the clay background, as the background itself lacks structural borders.

## Layout & Spacing
The layout follows a **fluid grid** model with significant breathing room. Because the UI relies on soft shadows rather than hard lines, white space (or "clay space") is the primary tool for grouping elements. 

- **Desktop:** 12-column grid with 24px gutters and wide 64px margins.
- **Mobile:** 4-column grid with 16px margins. 
- **Rhythm:** All spacing must be a multiple of 8px. Use larger internal padding (min 24px) for cards to ensure shadows have room to "breath" without clipping or overlapping adjacent content.

## Elevation & Depth
Depth is the core of this design system. It is achieved through a dual-shadow technique that simulates a light source coming from the top-left (135 degrees).

- **Raised Surfaces (Extruded):** Use a light shadow on the top-left (White, 60% opacity) and a dark shadow on the bottom-right (Black, 8% opacity). This makes elements appear to pop out of the page.
- **Pressed Surfaces (Inset):** Use an inner shadow. The top-left gets the dark shadow (Black, 6% opacity) and the bottom-right gets the light shadow (White, 50% opacity). This makes elements appear carved into the surface.
- **Focus States:** When an element is focused, use a subtle Indigo glow or a transition from Raised to Pressed state.

## Shapes
Shapes must be consistently rounded to maintain the organic, tactile feel. Sharp corners are strictly prohibited as they break the illusion of a molded surface.

- **Standard Elements:** 0.5rem (8px) radius for small tags or chips.
- **Interactive Elements:** 1rem (16px) radius for buttons and inputs.
- **Containers:** 1.5rem (24px) radius for cards and modal overlays.
- **Pills:** Full rounding for toggles and status indicators.

## Components
Consistent application of the "Extruded Light" philosophy across components:

- **Cards:** Use the **Raised** shadow token. Padding should be 24px. Content inside should be flat or use further inset elements.
- **Buttons:** 
  - **Default:** Raised style with Medium weight text.
  - **Active/Pressed:** Transition to **Inset** shadow style.
  - **Primary:** Use Indigo for the text and icon color, never as a solid background fill (which would break the neomorphic effect).
- **Input Fields:** Use the **Inset** shadow style by default to look "carved" into the surface. On focus, the inset shadow can deepen or a subtle Indigo stroke can be added.
- **Toggles & Sliders:** The track must be **Inset**, while the thumb/handle must be **Raised**. This creates a physical metaphor of a switch sitting inside a groove.
- **Lists:** Items should be separated by space rather than dividers. Active list items can take on a subtle Inset shape to indicate selection.
- **Chips:** Small raised surfaces with label-sm typography.