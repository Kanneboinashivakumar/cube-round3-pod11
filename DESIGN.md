---
name: DockProof Receiving
description: A calm, evidence-first receiving workspace for warehouse teams.
colors:
  canvas: "#f5f6f4"
  panel: "#ffffff"
  ink: "#181a1b"
  muted: "#62696c"
  quiet: "#62696c"
  line: "#e1e4e2"
  line-strong: "#cdd2cf"
  accent: "#4b556b"
  accent-strong: "#354055"
  accent-soft: "#eceef2"
  green: "#286b55"
  green-soft: "#eaf3ef"
  amber: "#815512"
  amber-soft: "#f7f0df"
  red: "#a33f35"
  red-soft: "#f7eae8"
typography:
  display:
    fontFamily: "Manrope, sans-serif"
    fontSize: "27px"
    fontWeight: 750
    lineHeight: 1.15
    letterSpacing: "-0.035em"
  title:
    fontFamily: "Manrope, sans-serif"
    fontSize: "14px"
    fontWeight: 700
    lineHeight: 1.3
  body:
    fontFamily: "DM Sans, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.45
  field:
    fontFamily: "DM Sans, sans-serif"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.4
  action:
    fontFamily: "DM Sans, sans-serif"
    fontSize: "12px"
    fontWeight: 700
    lineHeight: 1.3
  label:
    fontFamily: "DM Sans, sans-serif"
    fontSize: "11px"
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "0.04em"
rounded:
  sm: "4px"
  md: "5px"
  search: "6px"
  lg: "7px"
  scrollbar: "9px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.panel}"
    typography: "{typography.action}"
    rounded: "{rounded.md}"
    padding: "0 13px"
    height: "36px"
  button-secondary:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    typography: "{typography.action}"
    rounded: "{rounded.sm}"
    padding: "0 13px"
    height: "36px"
  input:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    typography: "{typography.field}"
    rounded: "{rounded.sm}"
    padding: "7px 9px"
    height: "35px"
  search-field:
    backgroundColor: "#fafbf9"
    textColor: "{colors.ink}"
    typography: "{typography.field}"
    rounded: "{rounded.search}"
    padding: "0 10px"
    height: "36px"
  status-pass:
    backgroundColor: "{colors.green-soft}"
    textColor: "{colors.green}"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    padding: "2px 8px"
    height: "22px"
  status-exception:
    backgroundColor: "{colors.red-soft}"
    textColor: "{colors.red}"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    padding: "2px 8px"
    height: "22px"
  panel:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: "16px"
---

# Design System: DockProof Receiving

## Overview

**Creative North Star: “The Receiving Status Board”**

The supplied warehouse dashboard is the visual anchor: a compact WMS frame, legible operational totals, a high-utility left rail, and a table that keeps current work visible. DockProof carries that familiar operating rhythm into the receiving task, where the object of attention is an auditable shipment decision rather than a general warehouse KPI.

The surface is restrained and evidence-first. Neutral panels and fine rules preserve scanability; muted navy marks primary actions and selected navigation; green, amber, and red communicate pass, uncertainty, and exception.

**Key Characteristics:**
- Familiar warehouse navigation and dense, scannable ledger.
- A quiet neutral frame with semantic color reserved for decisions.
- Clear hierarchy for operational states and decision context.

## Colors

The palette is low-chroma and operational: neutral structure carries most of the interface, while semantic hues have a single job.

### Primary
- **Slate Navy** (`#4b556b`): Primary buttons, selected navigation details, and focus outlines.
- **Deep Slate Navy** (`#354055`): Hover state for primary actions.

### Neutral
- **Soft Warehouse Canvas** (`#f5f6f4`): Main application background.
- **Paper Panel** (`#ffffff`): Cards, tables, top bar, and fields.
- **Near-Black Ink** (`#181a1b`): Headings and primary content.
- **Utility Gray** (`#62696c`): Body support copy, labels, and quiet text.
- **Divider Gray** (`#e1e4e2`): Panel and table boundaries.
- **Strong Divider** (`#cdd2cf`): Form outlines and stronger separators.

### Named Rules
**The Meaningful Color Rule.** Use green, amber, and red only to communicate pass, uncertainty, and exception; do not use them as decoration.

## Typography

**Display Font:** Manrope (sans-serif fallback)

**Body Font:** DM Sans (sans-serif fallback)

**Label/Mono Font:** DM Sans for labels; system monospace only for serialized JSON and code-like values.

**Character:** Manrope gives page and panel headings a compact, confident hierarchy. DM Sans stays neutral and highly readable across operational labels, forms, and dense tables.

### Hierarchy
- **Display** (750, 27px, 1.15): Page title.
- **Title** (700, 14px, 1.3): Panel headings; form headings may rise to 15px.
- **Body** (400, 14px, 1.45): Default copy and reading text; compact descriptions and dense data step down to 10–13px.
- **Field** (400, 12px, 1.4): Form values and search input text.
- **Label** (700, 9–11px, 1.3, 0.04–0.13em tracking): Table headers, metadata, and compact status text; uppercase is reserved for short labels.

## Layout

At desktop widths, a 64px top bar anchors a 224px receiving sidebar; the content area begins below the bar and to the right of the rail. Content uses a compact operational grid with a primary work area and supporting panels. Summary metrics share one horizontal strip with dividers rather than separate oversized cards. Tables are intentionally dense, with horizontal overflow contained inside the table region.

At 850px, the dashboard becomes one column while the sidebar narrows. At 600px, the navigation becomes an icon rail at the bottom, metrics form a two-by-two grid, and detail layouts collapse to one column. The mobile top bar keeps the workspace identity and a shrinking search field visible without horizontal page overflow.

Use an operational spacing rhythm centered on 4, 8, 12, 16, and 24px, with denser 9–13px table and control insets where shown in the implementation.

## Elevation & Depth

Depth is primarily structural: white panels sit on the softly tinted canvas and are separated by 1px rules. The single ambient shadow (`0 1px 2px rgb(19 25 24 / 5%)`) only softens panels; it must not compete with the dividers or make the dashboard feel floating.

**The Quiet Surface Rule.** Prefer a clear border or tonal change; keep shadows subtle and rare.

## Shapes

Use compact, near-square corners: 4px for filter and form fields, 5px for buttons and check surfaces, 6px for the global search, and 7px for major panels. The custom scrollbar thumb and small count badges use a 9px capsule. Status chips stay compact and lightly rounded. Avoid thick colored outlines on rounded containers; color belongs in status text and surface, not a heavy edge.

## Components

### Buttons
- **Shape:** Compact corners (5px primary, 4px secondary).
- **Primary:** Slate Navy with white text; 36px high and 13px horizontal padding.
- **Hover / Focus:** Deep Slate Navy on hover; keyboard focus uses the global 2px Slate Navy outline.
- **Secondary:** White surface with a 1px strong-neutral outline.

### Chips
- **Style:** Compact 4px status tags with a tinted semantic surface and darker semantic text.
- **State:** Green for pass/clean, amber for uncertain/review/pending, red for exception/fail.

### Cards / Containers
- **Corner Style:** 7px for panels, 1px neutral outline, white fill.
- **Shadow Strategy:** One very subtle 1px/2px ambient shadow; use the line as the main separator.
- **Internal Padding:** 16–17px desktop, 12–13px mobile.

### Inputs / Fields
- **Style:** White field, 1px strong-neutral stroke, 4px corners, 35px minimum height.
- **Focus:** Accent border and visible 2px Slate Navy keyboard ring.
- **Error / Disabled:** Errors use the red semantic vocabulary with explicit recovery copy; disabled actions remain visibly muted.

### Navigation
- **Style:** White top bar and side rail, compact DM Sans labels, authored 16–18px outline SVG icons. The current navigation contains receiving destinations and supporting catalogue, quality, and settings references.
- **Default / Hover / Active:** Neutral text; light-gray hover; soft neutral selected surface with stronger ink.
- **Mobile:** Fixed bottom icon navigation with accessible text labels and a selected neutral tile.

## Do's and Don'ts

### Do:
- **Do** preserve the compact WMS frame and its clear separation between navigation, work area, and supporting panels.
- **Do** use semantic color to clarify decision states while keeping neutral structure dominant.
- **Do** contain wide table overflow inside its own region.

### Don't:
- **Don't** use semantic colors as decoration or add thick accent borders to rounded panels.
- **Don't** hide wide table columns by clipping the page; keep overflow within the table region.
