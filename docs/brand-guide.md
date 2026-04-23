# Brand Guide — docubase

Version 1.1 | April 2026

---

## 1. Product Name

### **docubase**

Pronounced: *oh-pus EK-oh*

**Name etymology:**
- *Opus* — Latin for "the work." The thing you've made. Your repositories, projects, portfolios, career history — all of it.
- *Echo* — Greek, the voice that answers back. The conversational layer. Visitors ask; your work responds.
- Together: **your work, speaking back** — an intelligent twin that holds a conversation on your behalf.

**Why docubase:**
- Encodes all three core product aspects in two words: work, twin, conversation
- Not boxed into developer or repo territory — covers career twins, portfolio twins, project twins equally
- No real brand footprint in the SaaS or AI space — fully ownable
- Internationally readable — both roots are recognisable across languages
- Works as a domain: `docubase.app`, `docubase.io`, `docubase.dev`
- Scales to every use case: an docubase for your project, your career, your portfolio, your knowledge

**Tagline:** *Your work, in conversation.*

**Secondary tagline options:**
- *The AI that speaks for your work*
- *Share what you've built. Without the exposure.*
- *An intelligent twin for every project, profile, and portfolio*
- *Let people talk to your work*

---

### Alternative name candidates (reserved)

| Name | Rationale |
|------|-----------|
| **ImagoVox** | *imago* (likeness) + *vox* (voice) — "your likeness, speaking" |
| **TwinFolio** | Descriptive fallback — twin + portfolio |
| **AnimaVox** | *anima* (soul, essence) + *vox* — more poetic, career-facing |
| **OpusVox** | *opus* + *vox* — "the work, given voice" — close second |

**Decision:** docubase is the name. The tagline "Your work, in conversation" is a direct English translation of the name itself.

---

## 2. Brand Personality

docubase should feel like the smartest person in the room who never makes you feel small.

Four personality traits that must coexist in every design and copy decision:

| Trait | What it means in practice |
|-------|--------------------------|
| **Trustworthy** | Visitors feel safe — they know what the twin can and cannot say. Nothing feels leaked or accidental. |
| **Intelligent** | Answers feel precise and grounded, not generic. The product clearly knows something. |
| **Minimal** | The UI gets out of the way. The conversation is the product. No clutter. |
| **Warm** | Despite being technical, it never feels cold. A recruiter landing on a career twin should feel welcomed, not interrogated. |

**Brand voice — written copy:**
- Short sentences. Direct. No filler.
- Technical accuracy without jargon walls
- Never oversell. Never hedge too much.
- Confident, not arrogant
- Human, not robotic

**What docubase is NOT:**
- Not a chatbot service
- Not a GitHub wrapper
- Not a documentation tool
- Not a portfolio template

---

## 3. Color System

### Philosophy
The palette must work for two very different audiences simultaneously: a developer building their twin (dark, focused, technical), and a recruiter or client visiting a public page (light, clean, professional). The system must be excellent in both dark and light modes.

Color choices are inspired by the idea of **bioluminescence** — light that comes from within, intelligence that surfaces naturally from depth.

---

### Primary Palette

| Name | Hex | Usage |
|------|-----|-------|
| **Void** | `#0A0A0F` | Dark mode background, primary dark surface |
| **Ink** | `#13131A` | Dark mode card/panel backgrounds |
| **Slate** | `#1E1E2E` | Dark mode elevated surfaces, sidebar |
| **Mist** | `#F5F5F8` | Light mode background |
| **Cloud** | `#FFFFFF` | Light mode card/panel backgrounds |
| **Stone** | `#6B7280` | Secondary text, placeholder text |
| **Ash** | `#9CA3AF` | Tertiary text, disabled states |

---

### Brand Colors (accent system)

| Name | Hex | Usage |
|------|-----|-------|
| **Iris** | `#6366F1` | Primary brand color — interactive elements, CTA buttons, active states |
| **Iris Light** | `#818CF8` | Hover states on dark backgrounds |
| **Iris Dim** | `#4F46E5` | Pressed/active states |
| **Iris Muted** | `#EEF2FF` | Light mode chip backgrounds, subtle highlights |
| **Teal** | `#14B8A6` | Success states, "ready" source indicators, positive feedback |
| **Teal Dim** | `#0F766E` | Teal hover/pressed |
| **Amber** | `#F59E0B` | Warning states, "ingesting" status |
| **Rose** | `#F43F5E` | Error states, destructive actions, blocked file indicators |

---

### Color Roles

| Role | Light Mode | Dark Mode |
|------|-----------|-----------|
| Page background | `#F5F5F8` | `#0A0A0F` |
| Card/panel background | `#FFFFFF` | `#13131A` |
| Elevated surface | `#F9F9FB` | `#1E1E2E` |
| Border | `#E5E7EB` | `#2D2D3F` |
| Primary text | `#111827` | `#F1F5F9` |
| Secondary text | `#6B7280` | `#94A3B8` |
| Disabled text | `#D1D5DB` | `#475569` |
| Brand primary | `#6366F1` | `#818CF8` |
| Brand CTA button | `#6366F1` | `#6366F1` |
| CTA button text | `#FFFFFF` | `#FFFFFF` |
| Success | `#14B8A6` | `#2DD4BF` |
| Warning | `#F59E0B` | `#FCD34D` |
| Error | `#F43F5E` | `#FB7185` |

---

### Gradient — the docubase signature

The docubase gradient is used sparingly: landing page hero, empty state illustrations, and the workspace page header. It should feel like light seen through deep water.

```
docubase-gradient: linear-gradient(135deg, #6366F1 0%, #14B8A6 100%)
```

Used on:
- Public page header bands
- Onboarding welcome screen
- "Twin ready" celebration moment
- Embed widget top bar accent

Never used on:
- Body backgrounds
- Card surfaces
- Buttons (use solid `#6366F1`)
- Text (use solid colors for legibility)

---

## 4. Typography

### Philosophy
Two typefaces only. Never more. The system must be legible at every size, from a recruiter's phone to a developer's 4K monitor.

---

### Typefaces

**Display & Headings: Geist**
- Source: Vercel open source — `https://vercel.com/font`
- Weights used: 400 (Regular), 600 (SemiBold), 700 (Bold)
- Used for: page titles, twin names, section headers, marketing headings
- Why: technically precise, modern without being cold, excellent legibility at large sizes, zero-cost open source

**Body & UI: Inter**
- Source: Google Fonts — variable font
- Weights used: 400 (Regular), 500 (Medium), 600 (SemiBold)
- Used for: body text, UI labels, buttons, input fields, chat messages, captions
- Why: the gold standard for interface legibility, variable font (single file, full weight range), universally supported

---

### Type Scale

| Token | Size | Weight | Line Height | Usage |
|-------|------|--------|-------------|-------|
| `display-xl` | 56px | 700 | 1.1 | Marketing hero headline |
| `display-lg` | 40px | 700 | 1.15 | Page section headline |
| `display-md` | 32px | 600 | 1.2 | Card headline, modal title |
| `heading-lg` | 24px | 600 | 1.3 | Section heading |
| `heading-md` | 20px | 600 | 1.3 | Card title, sidebar section |
| `heading-sm` | 16px | 600 | 1.4 | Group label, nav item |
| `body-lg` | 16px | 400 | 1.6 | Main body text |
| `body-md` | 14px | 400 | 1.6 | UI body, chat message text |
| `body-sm` | 13px | 400 | 1.5 | Secondary information, captions |
| `label-md` | 14px | 500 | 1.4 | Button text, form labels |
| `label-sm` | 12px | 500 | 1.4 | Chip labels, status badges |
| `mono` | 13px | 400 | 1.6 | Code snippets (if shown), file paths |

**Monospace font for code:** `JetBrains Mono` or system fallback `ui-monospace, monospace`

---

### Typography rules

- Never use more than two weights in a single component
- Heading font (Geist) never appears below 16px
- Body text minimum 14px
- Line height never below 1.4 for readable blocks
- Letter-spacing: `-0.02em` on headings above 24px; `0` on body text
- All caps only for: status badges, keyboard shortcut labels — never for headings or body

---

## 5. Spacing & Layout

### Spacing scale (4px base unit)

| Token | Value | Usage |
|-------|-------|-------|
| `space-1` | 4px | Tight internal padding (icon + label gap) |
| `space-2` | 8px | Compact component padding |
| `space-3` | 12px | Default small padding |
| `space-4` | 16px | Default component padding |
| `space-5` | 20px | Comfortable padding |
| `space-6` | 24px | Section internal padding |
| `space-8` | 32px | Section gap |
| `space-10` | 40px | Large section gap |
| `space-12` | 48px | Page section padding |
| `space-16` | 64px | Hero/marketing spacing |

### Border radius

| Token | Value | Usage |
|-------|-------|-------|
| `radius-sm` | 6px | Buttons, inputs, small chips |
| `radius-md` | 10px | Cards, panels, dropdowns |
| `radius-lg` | 16px | Modals, large cards, chat container |
| `radius-xl` | 24px | Hero cards, feature sections |
| `radius-full` | 9999px | Pills, avatar circles, status dots |

### Elevation (shadows)

| Token | Value | Usage |
|-------|-------|-------|
| `shadow-sm` | `0 1px 3px rgba(0,0,0,0.08)` | Cards at rest |
| `shadow-md` | `0 4px 12px rgba(0,0,0,0.10)` | Hover cards, dropdowns |
| `shadow-lg` | `0 8px 30px rgba(0,0,0,0.14)` | Modals, floating panels |
| `shadow-iris` | `0 4px 20px rgba(99,102,241,0.25)` | Brand CTA buttons on hover |

---

## 6. Component Patterns

### Buttons

Three variants only:

**Primary** — `bg: #6366F1, text: white, border: none`
Used for: primary CTA (Create Twin, Share, Send message)

**Secondary** — `bg: transparent, text: #6366F1, border: 1px solid #6366F1`
Used for: secondary actions alongside a primary

**Ghost** — `bg: transparent, text: primary-text, border: none`
Used for: nav items, sidebar actions, tertiary actions

Button height: 40px (default), 32px (compact), 48px (large/CTA)
Button padding: 16px horizontal on default

**Button states:**
- Default → Hover: background lightens 8%, shadow-iris appears, 150ms ease
- Hover → Active/Pressed: background darkens 6%, shadow disappears, 80ms ease
- Default → Loading: label fades out, spinner fades in, width locked, 150ms
- Loading → Success: spinner becomes checkmark, 200ms, auto-clears after 1.5s
- Disabled: 40% opacity, cursor not-allowed

---

### Chat message bubbles

**User message:**
- Background: `#6366F1`
- Text: white
- Border radius: 16px 16px 4px 16px (sharp bottom-right corner — pointing toward user)
- Max width: 72% of container
- Padding: 12px 16px

**Assistant message:**
- Light mode background: `#F1F5F9`
- Dark mode background: `#1E1E2E`
- Text: primary text color
- Border radius: 16px 16px 16px 4px (sharp bottom-left corner — pointing toward assistant)
- Max width: 82% of container
- Padding: 12px 16px

**Source reference indicator:**
When a response references a specific source section, show a small pill below the message:
- `[src/auth/service.py]` in `label-sm` weight
- Background: `iris-muted` (#EEF2FF)
- Text: `#6366F1`
- Only shown if `allow_code_snippets` is enabled or source is a doc file

**Typing / streaming indicator:**
Three dots animating in sequence (not simultaneously). Each dot: 6px diameter, `#6366F1`, 400ms stagger.

---

### Status badges

| Status | Background | Text | Dot color |
|--------|-----------|------|-----------|
| Ready | `#ECFDF5` | `#065F46` | `#14B8A6` |
| Ingesting | `#FFFBEB` | `#92400E` | `#F59E0B` |
| Pending | `#F5F5F8` | `#6B7280` | `#9CA3AF` |
| Failed | `#FFF1F2` | `#9F1239` | `#F43F5E` |

Dot is 6px, `border-radius: full`, positioned left of label text.

---

### Twin card (owner dashboard)

Structure (top to bottom):
1. Twin name — `heading-md`
2. Description (1 line, truncated) — `body-sm`, secondary text
3. Source count badge — `label-sm`
4. Status badge — source ingestion status
5. Action row: Chat / Share / Config — ghost buttons

Card hover: `shadow-md`, 1px border shifts to `#6366F1` at 30% opacity, 150ms ease

---

### Public page layout

The public twin page and workspace page follow the same shell:

```
┌─────────────────────────────────┐
│  Header: Twin name + description│  56px height, subtle border-bottom
│  (docubase logo, bottom-right)     │
├─────────────────────────────────┤
│                                 │
│                                 │
│         Chat area               │  flex-1, overflow-y-auto
│                                 │
│                                 │
├─────────────────────────────────┤
│  Input bar                      │  72px height
│  [    Ask me anything...    ] → │
└─────────────────────────────────┘
```

Workspace page adds a left sidebar (240px) listing twin names for navigation.

---

## 7. Micro-interactions

Every interaction should feel **considered but not theatrical**. The rule: if you have to explain the animation, it's too much.

### Timing tokens

| Token | Value | Usage |
|-------|-------|-------|
| `duration-fast` | 100ms | State changes on focus, small toggles |
| `duration-base` | 150ms | Button hover, badge state change |
| `duration-smooth` | 200ms | Card hover, dropdown open |
| `duration-enter` | 250ms | Modal/panel enter |
| `duration-exit` | 200ms | Modal/panel exit (exits slightly faster than enter) |

All animations use `ease-out` for enter transitions. `ease-in` for exit. Never use linear on UI interactions.

---

### Specific micro-interactions

**Chat message send:**
1. User presses Send
2. Input clears immediately (no delay)
3. User bubble slides in from bottom-right, 200ms, `translateY(8px) → 0, opacity: 0 → 1`
4. Typing indicator appears below after 300ms — 3 dots in sequence
5. Typing indicator fades out as streaming text begins
6. Response text streams in character-by-character (not word-by-word — feels more natural)
7. After full response: source pills fade in below message if applicable, 150ms

**Twin card hover:**
1. Card: `shadow-sm → shadow-md`, 150ms
2. Left border: fades in at 30% iris color, 150ms
3. Action buttons: fade from 0 to 1 opacity (hidden at rest, visible on hover), 120ms

**Share button:**
1. Click: icon animates — link icon morphs to checkmark
2. "Link copied" tooltip appears above, fades in 150ms, persists 1.5s, fades out 200ms
3. No page disruption — tooltip floats, doesn't push layout

**Source status change (ingesting → ready):**
1. Amber dot pulses once (scale 1 → 1.4 → 1, 400ms) while ingesting
2. When status flips to ready: dot transitions amber → teal, 300ms cross-fade
3. Status text cross-fades, 150ms
4. Card border briefly glows teal: `box-shadow: 0 0 0 2px #14B8A6`, fades out over 600ms

**Chat input focus:**
1. Border: `#E5E7EB → #6366F1`, 150ms
2. Subtle `shadow-iris` appears, 150ms
3. Placeholder text fades slightly (opacity 0.6 → 0.4)

**Empty state (no twins yet):**
The docubase gradient blob animates slowly — a gentle, breathing pulse, scale 1 → 1.03 → 1 on 4s loop, `ease-in-out`. Not distracting, just alive.

**Page load — skeleton screens:**
Cards render as skeleton placeholders before data loads.
Skeleton: base color `#E5E7EB` (light) or `#1E1E2E` (dark), shimmer animation moving left to right at 1.5s, linear, infinite.
No spinner for page-level loads — skeletons feel faster and more polished.

**Modal enter/exit:**
- Enter: `scale(0.96) → scale(1), opacity: 0 → 1`, 250ms ease-out
- Exit: `scale(1) → scale(0.96), opacity: 1 → 0`, 200ms ease-in
- Backdrop: `opacity: 0 → 0.5`, 200ms ease-out

---

## 8. Iconography

Use **Lucide React** icon set throughout. It is the consistent choice across the modern developer tool ecosystem (Linear, Vercel, Supabase all use or are compatible with it).

Icon sizes:
- `16px` — inline with text labels, status indicators
- `20px` — default UI icon size (nav, buttons, actions)
- `24px` — feature section icons, empty state icons

Icon color: always inherits text color of its context. Never a fixed color unless it's a status indicator.

Icons in buttons: always left of label text, never right (except the send button arrow, which points right).

---

## 9. Illustration / Visual style

No complex illustrations. docubase uses **geometric, abstract shapes** as visual accents — not mascots, not character illustrations.

The primary visual device is a **soft radial gradient orb** — representing a twin, a node of intelligence.

Orb properties:
- Base: docubase gradient (`#6366F1 → #14B8A6`)
- Soft gaussian blur: `filter: blur(60px)`
- Opacity: 0.35 at rest, 0.45 on hover contexts
- Used behind hero text on landing page, behind empty states, behind the welcome screen

This keeps the visual language consistent, scalable, and impossible to accidentally misuse.

---

## 10. Motion principles summary

| Principle | Rule |
|-----------|------|
| Purposeful | Every animation communicates state change, not decoration |
| Fast | Nothing slower than 300ms on interactive elements |
| Consistent | Same duration tokens used everywhere — no one-off timings |
| Subtle | If you notice the animation more than the result, it's too much |
| Accessible | All motion respects `prefers-reduced-motion` — when set, transitions drop to 0ms or simple fade |

---

## 11. Application to surfaces

### Owner dashboard (authenticated)
- Dark mode default (can be toggled)
- Full Iris accent throughout
- Dense information layout — developers expect it
- Sidebar navigation, not top nav

### Public twin page (`/t/:slug`)
- Light mode default
- Twin's `accentColor` overrides Iris if set
- Maximum whitespace
- Only the twin name, description, and chat — nothing else
- docubase branding is subtle (small logo, bottom-right footer)

### Public workspace page (`/w/:slug`)
- Light mode default
- Left sidebar with twin list
- Right: full-height chat
- Feels like a clean portfolio, not a dashboard
- Zero technical jargon visible to visitors

### Embed widget
- Floating button (bottom-right, 52px circle, Iris background, white icon)
- Expands to 380px × 560px panel on click
- Panel: `radius-lg`, `shadow-lg`, light mode only
- Header bar: twin name, close button
- Chat interface inside
- Powered by docubase — small link in footer

---

## 12. CSS design tokens (implementation reference)

```css
:root {
  /* Brand */
  --color-iris: #6366F1;
  --color-iris-light: #818CF8;
  --color-iris-dim: #4F46E5;
  --color-iris-muted: #EEF2FF;
  --color-teal: #14B8A6;
  --color-amber: #F59E0B;
  --color-rose: #F43F5E;

  /* Neutrals - Light */
  --color-bg: #F5F5F8;
  --color-surface: #FFFFFF;
  --color-surface-raised: #F9F9FB;
  --color-border: #E5E7EB;
  --color-text-primary: #111827;
  --color-text-secondary: #6B7280;
  --color-text-tertiary: #9CA3AF;

  /* Spacing */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;
  --space-10: 40px;
  --space-12: 48px;

  /* Radius */
  --radius-sm: 6px;
  --radius-md: 10px;
  --radius-lg: 16px;
  --radius-xl: 24px;
  --radius-full: 9999px;

  /* Shadows */
  --shadow-sm: 0 1px 3px rgba(0,0,0,0.08);
  --shadow-md: 0 4px 12px rgba(0,0,0,0.10);
  --shadow-lg: 0 8px 30px rgba(0,0,0,0.14);
  --shadow-iris: 0 4px 20px rgba(99,102,241,0.25);

  /* Duration */
  --duration-fast: 100ms;
  --duration-base: 150ms;
  --duration-smooth: 200ms;
  --duration-enter: 250ms;
  --duration-exit: 200ms;

  /* Typography */
  --font-display: 'Geist', system-ui, sans-serif;
  --font-body: 'Inter', system-ui, sans-serif;
  --font-mono: 'JetBrains Mono', ui-monospace, monospace;
}

[data-theme="dark"] {
  --color-bg: #0A0A0F;
  --color-surface: #13131A;
  --color-surface-raised: #1E1E2E;
  --color-border: #2D2D3F;
  --color-text-primary: #F1F5F9;
  --color-text-secondary: #94A3B8;
  --color-text-tertiary: #475569;
  --color-iris: #818CF8;
  --color-iris-muted: #1E1B4B;
  --shadow-sm: 0 1px 3px rgba(0,0,0,0.3);
  --shadow-md: 0 4px 12px rgba(0,0,0,0.35);
  --shadow-lg: 0 8px 30px rgba(0,0,0,0.4);
}

@media (prefers-reduced-motion: reduce) {
  * {
    transition-duration: 0ms !important;
    animation-duration: 0ms !important;
  }
}
```

---

## 13. What to build first (brand implementation order)

1. CSS design tokens file (`frontend/src/styles/tokens.css`)
2. Tailwind config extending with these tokens
3. Button component (all 3 variants, all 5 states)
4. ChatInterface with correct bubble styling and streaming animation
5. StatusBadge component
6. TwinCard component
7. Public twin page shell
8. Embed widget shell
9. Landing page (last — dependent on all components being stable)
