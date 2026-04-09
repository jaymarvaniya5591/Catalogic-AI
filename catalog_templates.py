"""
Catalog templates for "Create from Scratch" mode.
Defines product categories, question groups, and per-slot generation prompts.

Slot prompt_fragment template variables are filled at generation time using
compiled_attributes (the merged dict from user answers + defaults).

Typography reference (used in all prompts):
  - Font family: thin elegant sans-serif (Inter, Futura, or Gotham)
  - Text hierarchy:
      * Feature label / callout title: 11–13 px, ALL CAPS, letter-spacing 0.1em
      * Value text: 18–22 px, weight 300 (light), warm white #F5F0E8
      * Body descriptor: 12–14 px, weight 400, muted (#888888 or white 60%)
  - Accent color: warm gold #C4A265
  - Background for lifestyle/brand: very dark charcoal #141414 or #1C1C1C
  - Background for diagrams: clean soft white #F8F8F6 or light warm grey #EEECE8
  - All text overlays must be legible — contrast ratio > 4.5:1
  - Amazon A+ quality benchmark — every image should look like a premium brand A+ content panel
"""

# ─────────────────────────────────────────────────────────────────────────────
# HELPER: flatten question_groups → flat list for iteration
# ─────────────────────────────────────────────────────────────────────────────

def get_all_questions(category: str, product_type: str) -> list[dict]:
    """Return flat list of all questions for a product, preserving group order."""
    prod = (
        PRODUCT_CATALOG
        .get(category, {})
        .get("products", {})
        .get(product_type)
    )
    if not prod:
        return []
    out = []
    for group in prod.get("question_groups", []):
        for q in group.get("questions", []):
            out.append(q)
    return out


def get_defaults(category: str, product_type: str) -> dict:
    """Return {attribute_id: default_value} for every question that has one."""
    defaults = {}
    for q in get_all_questions(category, product_type):
        aid = q.get("attribute_id")
        dv = q.get("default_value")
        if aid and dv is not None:
            defaults[aid] = str(dv)
    return defaults


def get_catalog_slots(category: str, product_type: str) -> list[dict]:
    prod = (
        PRODUCT_CATALOG
        .get(category, {})
        .get("products", {})
        .get(product_type)
    )
    if not prod:
        return []
    return prod.get("catalog_slots", [])


# ─────────────────────────────────────────────────────────────────────────────
# MAIN CATALOG DATA
# ─────────────────────────────────────────────────────────────────────────────

PRODUCT_CATALOG: dict = {

    # ═══════════════════════════════════════════════════════════════
    # CATEGORY: BATHROOM PRODUCTS
    # ═══════════════════════════════════════════════════════════════
    "bathroom_products": {
        "label": "Bathroom Products",
        "products": {

            # ─────────────────────────────────────────
            # PRODUCT: TOILET / EWC
            # Reference listing: Hindware Prima B0FCG1T4PW
            # ─────────────────────────────────────────
            "toilet": {
                "label": "Toilets / EWC",

                # ── Questions ─────────────────────────────────────────────────
                "question_groups": [

                    # GROUP 1: Product Basics
                    {
                        "group_id": "basics",
                        "group_label": "Product Basics",
                        "questions": [
                            {
                                "id": "q_product_name",
                                "text": "Product / Brand Name",
                                "context": "Used in branding images and feature callouts.",
                                "type": "text",
                                "default_value": "Prima",
                                "attribute_id": "product_name",
                            },
                            {
                                "id": "q_product_type",
                                "text": "Toilet Type",
                                "context": "One-Piece has tank and bowl fused. Two-Piece has separate tank. Wall-Hung mounts on wall.",
                                "type": "choice",
                                "options": ["One-Piece", "Two-Piece", "Wall-Hung"],
                                "default_value": "One-Piece",
                                "attribute_id": "product_type",
                            },
                            {
                                "id": "q_color",
                                "text": "Color / Finish",
                                "context": "Auto-detected from your product image. Edit if needed.",
                                "type": "text",
                                "default_value": "Star White",
                                "attribute_id": "product_color",
                                "ai_detected": True,
                            },
                            {
                                "id": "q_material",
                                "text": "Body Material",
                                "context": "The ceramic compound used for the toilet body.",
                                "type": "choice",
                                "options": ["Ceramic", "Vitreous China", "Porcelain", "Fireclay"],
                                "default_value": "Ceramic",
                                "attribute_id": "material",
                            },
                            {
                                "id": "q_bowl_shape",
                                "text": "Bowl Shape",
                                "context": "As viewed from above.",
                                "type": "choice",
                                "options": ["Square", "Round", "Elongated", "D-Shape"],
                                "default_value": "Square",
                                "attribute_id": "bowl_shape",
                            },
                        ],
                    },

                    # GROUP 2: Dimensions
                    {
                        "group_id": "dimensions",
                        "group_label": "Dimensions",
                        "questions": [
                            {
                                "id": "q_length_cm",
                                "text": "Overall Length (cm)",
                                "context": "Front-to-back measurement from front rim to back of tank.",
                                "type": "text",
                                "default_value": "64.5",
                                "attribute_id": "overall_length",
                            },
                            {
                                "id": "q_width_cm",
                                "text": "Overall Width (cm)",
                                "context": "Side-to-side measurement at the widest point.",
                                "type": "text",
                                "default_value": "35.5",
                                "attribute_id": "overall_width",
                            },
                            {
                                "id": "q_height_cm",
                                "text": "Overall Height (cm)",
                                "context": "Floor to top of tank lid.",
                                "type": "text",
                                "default_value": "74.5",
                                "attribute_id": "overall_height",
                            },
                            {
                                "id": "q_seat_height_cm",
                                "text": "Seat Height (cm)",
                                "context": "Floor to top of closed seat — comfort standard is 38–43 cm.",
                                "type": "text",
                                "default_value": "39.5",
                                "attribute_id": "seat_height",
                            },
                            {
                                "id": "q_weight_kg",
                                "text": "Product Weight (kg)",
                                "context": "Shipping/installation weight of the complete unit.",
                                "type": "text",
                                "default_value": "43.5",
                                "attribute_id": "weight_kg",
                            },
                        ],
                    },

                    # GROUP 3: Flushing System
                    {
                        "group_id": "flush",
                        "group_label": "Flushing System",
                        "questions": [
                            {
                                "id": "q_flush_type",
                                "text": "Flush Technology",
                                "context": "Wash Down is direct gravity. Siphonic uses suction. Tornado uses rim jets.",
                                "type": "choice",
                                "options": ["Wash Down", "Siphonic", "Tornado Flush", "Rimless Direct"],
                                "default_value": "Wash Down",
                                "attribute_id": "flush_type",
                            },
                            {
                                "id": "q_flush_mode",
                                "text": "Flush Mode",
                                "context": "Dual Flush has 2 buttons (full/half). Single Flush has one.",
                                "type": "choice",
                                "options": ["Dual Flush", "Single Flush"],
                                "default_value": "Dual Flush",
                                "attribute_id": "flush_mode",
                            },
                            {
                                "id": "q_flush_volume",
                                "text": "Flush Volumes (litres)",
                                "context": "For dual flush: full / half flush volumes. E.g. '6 / 3 litres'",
                                "type": "text",
                                "default_value": "6 / 3 litres",
                                "attribute_id": "flush_volume",
                            },
                            {
                                "id": "q_water_rating",
                                "text": "Water Efficiency Rating",
                                "context": "Any official rating or label for water saving.",
                                "type": "choice",
                                "options": ["Water Efficient", "WELS 4 Star", "BIS Certified", "Standard"],
                                "default_value": "Water Efficient",
                                "attribute_id": "water_rating",
                            },
                        ],
                    },

                    # GROUP 4: Trap & Installation
                    {
                        "group_id": "trap",
                        "group_label": "Trap & Installation",
                        "questions": [
                            {
                                "id": "q_trap_type",
                                "text": "Trap Type",
                                "context": "S-Trap exits downward through floor. P-Trap exits through wall.",
                                "type": "choice",
                                "options": ["S-Trap", "P-Trap", "Both S & P-Trap"],
                                "default_value": "S-Trap",
                                "attribute_id": "trap_type",
                            },
                            {
                                "id": "q_trap_distance_mm",
                                "text": "Trap Distance / Rough-In (mm)",
                                "context": "Distance from wall to centre of outlet. Standard Indian: 180–220 mm.",
                                "type": "text",
                                "default_value": "220",
                                "attribute_id": "rough_in_inches",
                            },
                            {
                                "id": "q_installation_type",
                                "text": "Installation Type",
                                "context": "",
                                "type": "choice",
                                "options": ["Floor Mounted", "Wall Mounted"],
                                "default_value": "Floor Mounted",
                                "attribute_id": "installation_type",
                            },
                        ],
                    },

                    # GROUP 5: Seat & Comfort
                    {
                        "group_id": "seat",
                        "group_label": "Seat & Comfort",
                        "questions": [
                            {
                                "id": "q_seat_close",
                                "text": "Seat Closing Mechanism",
                                "context": "Soft Close uses hydraulic hinges to close silently.",
                                "type": "choice",
                                "options": ["Soft Close", "Standard Close"],
                                "default_value": "Soft Close",
                                "attribute_id": "seat_close_type",
                            },
                            {
                                "id": "q_seat_material",
                                "text": "Seat Material",
                                "context": "PP is lightweight. Duroplast is denser and more rigid. UF is premium.",
                                "type": "choice",
                                "options": ["PP (Polypropylene)", "Duroplast", "UF (Urea Formaldehyde)"],
                                "default_value": "PP (Polypropylene)",
                                "attribute_id": "seat_material",
                            },
                            {
                                "id": "q_weight_capacity",
                                "text": "Weight Capacity (kg)",
                                "context": "Maximum supported user weight.",
                                "type": "text",
                                "default_value": "200",
                                "attribute_id": "weight_capacity_kg",
                            },
                        ],
                    },

                    # GROUP 6: Quality & Warranty
                    {
                        "group_id": "quality",
                        "group_label": "Quality & Warranty",
                        "questions": [
                            {
                                "id": "q_firing_temp",
                                "text": "Firing Temperature (°C)",
                                "context": "Higher firing temperature = denser, harder, more vitrified ceramic.",
                                "type": "text",
                                "default_value": "1200",
                                "attribute_id": "firing_temp_c",
                            },
                            {
                                "id": "q_warranty_body",
                                "text": "Warranty – Ceramic Body (years)",
                                "context": "",
                                "type": "text",
                                "default_value": "10",
                                "attribute_id": "warranty_body_years",
                            },
                            {
                                "id": "q_warranty_fittings",
                                "text": "Warranty – Fittings & Seat (years)",
                                "context": "",
                                "type": "text",
                                "default_value": "1",
                                "attribute_id": "warranty_fittings_years",
                            },
                        ],
                    },

                    # GROUP 7: Features
                    {
                        "group_id": "features",
                        "group_label": "Features & Technology",
                        "questions": [
                            {
                                "id": "q_rimless",
                                "text": "Rimless / Box Rim",
                                "context": "Rimless bowls have no inner rim ledge, making cleaning easier.",
                                "type": "choice",
                                "options": ["Rimless", "Box Rim", "Standard Rim"],
                                "default_value": "Rimless",
                                "attribute_id": "rim_type",
                            },
                            {
                                "id": "q_glaze",
                                "text": "Special Glaze / Coating",
                                "context": "Anti-bacterial or nano glaze repels stains and bacteria.",
                                "type": "choice",
                                "options": ["Anti-Bacterial Glaze", "Nano Glaze", "Standard Glaze"],
                                "default_value": "Anti-Bacterial Glaze",
                                "attribute_id": "glaze_type",
                            },
                            {
                                "id": "q_skirted",
                                "text": "Base Style",
                                "context": "Fully Skirted means the plumbing is hidden behind a smooth ceramic panel.",
                                "type": "choice",
                                "options": ["Fully Skirted", "Semi-Skirted", "Open Base"],
                                "default_value": "Fully Skirted",
                                "attribute_id": "base_style",
                            },
                            {
                                "id": "q_rubber_bumpers",
                                "text": "Rubber Bumpers on Seat",
                                "context": "Prevent seat from sliding and protect bowl rim.",
                                "type": "choice",
                                "options": ["Yes", "No"],
                                "default_value": "Yes",
                                "attribute_id": "rubber_bumpers",
                            },
                        ],
                    },
                ],  # end question_groups

                # ── Catalog Slots ───────────────────────────────────────────
                # Slot 0 (hero) is handled by generate_hero_image(); listed here
                # so the frontend can show it in the slot list and skip it in
                # the SSE generation loop.
                "catalog_slots": [

                    # ── SLOT 0: Hero Shot ──────────────────────────────────
                    {
                        "slot_id": "hero",
                        "name": "Hero Shot",
                        "tagline": "Premium 3/4-angle product photo — the visual anchor",
                        "image_type": "hero",
                        "is_hero": True,  # handled by generate_hero_image(), not by the stream
                        "prompt_fragment": "",
                    },

                    # ── SLOT 1: Material & Ceramic Quality ─────────────────
                    {
                        "slot_id": "material_quality",
                        "name": "Material & Ceramic Quality",
                        "tagline": "Ceramic quality infographic — glaze tech, firing temp, 4 feature icons",
                        "image_type": "infographic",
                        "is_hero": False,
                        "prompt_fragment": """\
INTENT: Showcase the premium ceramic quality and surface technology of the {product_name} toilet. The toilet must look like a REAL PHOTOGRAPH — photorealistic, not a diagram.

COMPOSITION & LAYOUT:
This is a 1:1 square infographic panel with clean soft white-cream background throughout. Divide it into FIVE distinct zones:

  TOP ZONE (top 15%): Product name "{product_name}" in very thin widely-spaced uppercase letters, centered, on clean near-white background. Below it, a single thin gold hairline separator centered at about 40% of panel width.

  CENTER ZONE (middle 40%): The toilet product, viewed at a clean 3/4 front angle on a soft neutral surface with a subtle drop shadow. The ceramic surface must look PHOTOREALISTIC and IDENTICAL to IMAGE 1 (HERO) — same color ({product_color}), same exact shape, same gloss level. Product positioned slightly left of center. NO line-drawing or illustration style — this must look like a high-quality product photograph.

  RIGHT COLUMN (alongside center zone, 38% of panel width): A vertical list of 4 ceramic quality features, each in a small dark rounded card with a thin darker border. Each card contains:
      - A minimal single-color geometric icon on the left
      - Feature name in small gold uppercase letters
      - A short descriptor in small muted grey text below
    The 4 features:
      1. STAIN RESISTANT — "Micro-smooth glaze repels residues"
      2. EVERLASTING SHINE — "{glaze_type} for lasting brilliance"
      3. EASY CLEANING — "Rimless interior, no ledge to scrub"
      4. BACTERIA PREVENTION — "Anti-bacterial surface protection"

  BOTTOM BADGE ROW (bottom 15%): Centered row of 2 rectangular data badges on a slightly darker cream strip:
      Badge 1 — "FIRED AT {firing_temp_c}°C" with a small flame icon in gold
      Badge 2 — "{warranty_body_years} YEAR WARRANTY" with a shield icon in gold
    Both badges use small uppercase text in dark charcoal.

  FULL BACKGROUND: Very clean soft white-cream. No gradients. No lifestyle photography.

STYLE RULES:
  - The product must look like a real product photo — photorealistic ceramic with premium gloss sheen, not an illustration
  - Drop shadow under product: soft, subtle, offset downward, low opacity
  - Typography throughout: thin elegant sans-serif font. Do NOT write out font size numbers or hex color codes as text in the image
  - Zero clutter — generous white space between elements
  - Amazon A+ content panel quality — museum-clean layout
  - Do NOT add watermarks, logos, QR codes, or unspecified elements
  - 1:1 aspect ratio
""",
                    },

                    # ── SLOT 2: Flushing System ────────────────────────────
                    {
                        "slot_id": "flush_system",
                        "name": "Flushing System",
                        "tagline": "Realistic toilet cross-section — flush tech, dual-flush button, water rating",
                        "image_type": "functional",
                        "is_hero": False,
                        "prompt_fragment": """\
INTENT: Sell the {flush_type} flushing system of the {product_name} toilet — communicating its BENEFITS prominently, with a cross-section visualization layered on the actual product. This image must feel IMMERSIVE and premium — the real toilet from IMAGE 1 (HERO) fills the entire frame, with all text and diagrams as floating overlays on top, like a page from a luxury bathroom brand catalog.

OVERALL LAYOUT: 1:1 square panel. FULL-BLEED — the photorealistic product from IMAGE 1 (HERO) fills the entire frame as the base layer. All text and graphic elements are overlaid on top of the product and its bathroom environment. NO separate color band sections — everything floats over the image.

HEADING OVERLAY (top 18% of panel):
  A semi-transparent dark charcoal overlay strip (roughly top 18%) with soft gradient edges fading into the product image below — NOT a hard cut, it bleeds naturally into the photo.
  Inside this overlay, centered:
    Heading: «{flush_type}» in large thin warm-white uppercase letters
    Subline: «{flush_mode} · {flush_volume}» in smaller thin gold text
    A thin gold hairline below, centered, spanning ~30% of panel width

CROSS-SECTION VISUALIZATION (center-left of the product image):
  On the left/center portion of the product, a semi-transparent cutaway slice reveals the internal bowl and trap. The exterior product still looks photorealistic; the cutaway interior shows the flush mechanism as a clean diagram overlay:
    — If {flush_type} involves siphon/vacuum: show rim jet arrows (labeled «RIM JETS»), swirling translucent blue water, a vacuum zone in the trapway (labeled «VACUUM SUCTION» with inward arrows), an upward siphon arrow (labeled «SIPHON PULL»), and a downward exit arrow (labeled «OUTLET»)
    — If {flush_type} is wash-down/gravity: show bold downward cascade arrows from rim through bowl to outlet, labeled «DIRECT FLUSH»
    — If {flush_type} is tornado/jet: show angled rim nozzle jets creating a cyclone pattern, labeled «POWER JETS»
  All labels are floating pill-style callout boxes with dark semi-transparent backgrounds and warm-white text — NOT hard-edged blocks

BENEFIT CALLOUTS (right side, floating over the product):
  3 stacked benefit cards floating on the right 40% of the panel, with dark semi-transparent card backgrounds (glass-morphism style — blurred background, thin gold border):
    Derive the 3 most relevant consumer benefits from {flush_type} and {flush_mode}:
      - Siphon/vacuum → silent flush, complete evacuation, no residue
      - Wash-down/gravity → powerful force, reliable mechanism, low maintenance
      - Tornado/jet → 360° rim coverage, hygienic (no rim contact needed), powerful clean
      - Dual Flush → water saving with actual {flush_volume} values is a mandatory benefit
    Each card: a minimal gold icon + benefit heading in small gold uppercase + one-line description in small warm-white text

BOTTOM STATS OVERLAY (bottom 18%):
  A semi-transparent dark overlay strip (same style as the top — soft gradient edges, bleeds into the photo above):
  Three stat tiles inside, separated by thin vertical gold lines:
    Tile 1: Water-drop icon + flush volume from {flush_volume} in large thin warm-white + «FLUSH VOLUME» in tiny gold uppercase
    Tile 2: Certification icon + «{water_rating}» in large thin warm-white + «RATING» in tiny gold uppercase
    Tile 3: Gear icon + «{flush_type}» in large thin warm-white + «TECHNOLOGY» in tiny gold uppercase

STYLE RULES:
  - Full-bleed product photo is the foundation — NO hard-cut separate color bands
  - Top and bottom overlays must have soft gradient fade edges (not sharp rectangular cuts)
  - Floating cards use glassmorphism: semi-transparent dark backgrounds, subtle blur, thin gold border
  - Benefits are the priority — make the 3 benefit cards the most visually dominant overlay element
  - All text: thin elegant sans-serif. Render ONLY the «content words» — never render styling notes as image text
  - Amazon A+ luxury catalog quality — immersive, editorial, premium
  - 1:1 aspect ratio
""",
                    },

                    # ── SLOT 3: Dimensions Diagram ─────────────────────────
                    {
                        "slot_id": "dimensions",
                        "name": "Dimensions Diagram",
                        "tagline": "Technical side-elevation drawing with 6 measurement callouts",
                        "image_type": "dimensions",
                        "is_hero": False,
                        "prompt_fragment": """\
INTENT: Show the precise technical dimensions of the {product_name} toilet in a clean engineering-style technical drawing — like a Villeroy & Boch or TOTO catalog dimension sheet.

OVERALL LAYOUT: 1:1 square. Clean soft warm-white background throughout. No dark zones.

HEADER (top 12%): Centered text block:
  • Label "DIMENSIONS" in small muted grey uppercase letters with generous letter-spacing
  • Below it, product name "{product_name}" in large thin dark lettering

MAIN DIAGRAM (middle 76%):
Show the toilet in a precise SIDE ELEVATION VIEW (profile from the left side). This is a clean technical line-drawing — NOT a photograph: crisp dark outlines showing the product silhouette with dashed internal lines for hidden geometry. The toilet is centered, occupying roughly 55% of the panel width, with clear callout space on both sides.

SIX MEASUREMENT CALLOUTS radiating from the diagram:
  1. OVERALL HEIGHT — vertical double-headed arrow on the RIGHT side, spanning full floor-to-lid-top height. Label the arrow "{overall_height} cm" in bold dark text. Small gold uppercase label "HEIGHT" above the value.
  2. OVERALL LENGTH — horizontal double-headed arrow at the BOTTOM, spanning front-rim to back-of-tank. Label: "{overall_length} cm". Gold label "DEPTH" above.
  3. SEAT HEIGHT — vertical arrow on the LEFT side, floor to closed seat surface. Label: "{seat_height} cm". Gold label "SEAT HEIGHT" above.
  4. OVERALL WIDTH — shown as a small front-view inset thumbnail in the lower-right corner with a horizontal arrow. Label: "{overall_width} cm". Gold label "WIDTH".
  5. ROUGH-IN / TRAP DISTANCE — horizontal arrow at floor level, from wall to outlet center. Label: "{rough_in_inches} mm". Gold label "ROUGH-IN".
  6. PRODUCT WEIGHT — not an arrow but a small dark-background circular badge in the lower-left corner with white text: "{weight_kg} kg". Thin gold circular border around badge.

CALLOUT STYLE: Thin dashed extension lines, small solid arrowheads. Dimension values in bold dark text. Category labels in small gold uppercase above each value. All lines are crisp and precise.

BOTTOM STRIP (bottom 12%): Thin light grey bar at the bottom. Centered text: "FLOOR MOUNTED · {trap_type} · {installation_type}" in small muted grey. Thin gold divider line above this strip.

STYLE RULES:
  - This is a PURE TECHNICAL ILLUSTRATION — no product photograph anywhere in this slot
  - Clean white/cream background throughout — no gradients, no dark sections
  - All six dimension callouts must be clearly legible and non-overlapping
  - Do NOT write out font size numbers or CSS color codes as text in the image — only render the actual label and value content
  - Amazon A+ quality — the kind of precision dimension diagram found in premium bathroom brand catalogs
  - 1:1 aspect ratio
""",
                    },

                    # ── SLOT 4: Seat Features ──────────────────────────────
                    {
                        "slot_id": "seat_features",
                        "name": "Seat Cover Features",
                        "tagline": "Soft-close motion diagram + seat material & bumper icons",
                        "image_type": "infographic",
                        "is_hero": False,
                        "prompt_fragment": """\
INTENT: Highlight the premium seat cover features of the {product_name} toilet in a visually rich panel. The product from IMAGE 1 (HERO) must be the photorealistic visual anchor — seat feature callouts are overlaid ON TOP of the real product, not on an illustration.

OVERALL LAYOUT: 1:1 square panel.

BACKGROUND: The full panel uses the actual toilet product from IMAGE 1 (HERO) as its primary visual element. Show the product at a slight 3/4 angle, soft lighting, subtle dark-to-light radial vignette in the background (bathroom environment, very softly blurred).

TOP SECTION (top 20%): Dark semi-transparent overlay strip across the top of the image:
  Heading: «SEAT COVER FEATURES» in thin warm-white uppercase letters
  Subline: «{seat_close_type} · {seat_material}» in smaller gold text

SEAT MOTION CALLOUT (overlaid on the right side of the product image):
  Show the seat in TWO ghost-overlay positions — Position A: seat open/raised (shown as a light transparent outline), Position B: seat closed (shown as the solid real product). A graceful curved arc arrow sweeps from Position A down to Position B in warm gold, indicating the closing motion.
  If {seat_close_type} = "Soft Close": add a small badge near the arc showing «SOFT CLOSE» with a slow-descent icon.
  If {seat_close_type} = "Standard Close": the badge reads «STANDARD CLOSE» instead.

FEATURE CALLOUT LINES (3 thin gold lines radiating from the seat to label boxes on the right side):
  Callout 1 — arrow from seat hinge area:
    Label box: heading «{seat_close_type} HINGE» / description: if Soft Close then «Closes silently without slamming»; if Standard Close then «Reliable, durable hinge mechanism»
  Callout 2 — arrow from seat surface:
    Label box: «{seat_material} SEAT» (heading) / «Durable, hygienic, easy-wipe surface» (description)
  Callout 3 — arrow from seat underside:
    If {rubber_bumpers} = "Yes": Label box: «RUBBER BUMPERS» / «Anti-slip, protects bowl rim»
    If {rubber_bumpers} = "No": omit this callout and distribute space evenly between the two remaining callouts

BOTTOM BADGE ROW (bottom 15%): Semi-transparent dark strip across the bottom. Three badges in a row:
  Badge 1: Shield icon + «BIS APPROVED»
  Badge 2: Weight icon + «UP TO {weight_capacity_kg} KG»
  Badge 3: Warranty icon + «{warranty_fittings_years} YR WARRANTY»
  All in small uppercase white text.

STYLE RULES:
  - The product MUST look photorealistic in this image — identical to IMAGE 1 (HERO), not a flat line drawing
  - Callout lines are thin warm gold; label boxes are dark semi-transparent pills with light text
  - The seat ghost overlay (open position) must be very faint — just enough to show the arc of travel
  - Do NOT write out any styling notes as image text — only render the label content inside «» marks
  - Amazon A+ quality panel
  - 1:1 aspect ratio
""",
                    },

                    # ── SLOT 5: Installation & Trap ────────────────────────
                    {
                        "slot_id": "installation_trap",
                        "name": "Installation & Trap",
                        "tagline": "Realistic toilet cross-section — trap path, outlet, and rough-in measurement",
                        "image_type": "functional",
                        "is_hero": False,
                        "prompt_fragment": """\
INTENT: Show the plumbing installation details of the {product_name} toilet — specifically HOW the trap works, WHERE the water exits, and the rough-in distance. The image must feel REALISTIC — show the actual toilet from IMAGE 1 (HERO) in a cutaway cross-section revealing internal plumbing, NOT a bare line drawing.

OVERALL LAYOUT: 1:1 square panel. Upper 65% is clean warm-white background, lower 35% has a subtle rendered floor-tile texture (very light cream with barely-visible grout lines — just enough to show the floor context).

HEADER (top 15%):
  Centered text block:
  • Small gold uppercase label: "INSTALLATION GUIDE"
  • Below it, large thin dark text: "{trap_type} · {rough_in_inches} mm ROUGH-IN"
  • A thin grey hairline separator below

MAIN CROSS-SECTION VIEW (middle 70%):
Show the toilet in a SIDE-PROFILE CUT-AWAY VIEW. The toilet body (left 60% of panel) must look PHOTOREALISTIC on the outside — identical finish, color, and shape to IMAGE 1 (HERO). The right/interior half of the toilet body is cut away in a semi-transparent slice, revealing the internal plumbing path.

INTERNAL PLUMBING REVEALED (inside the cutaway):
  The key feature is showing the COMPLETE WATER JOURNEY from inlet to outlet:
  a) WATER INLET PATH: Show where the water supply enters the cistern — a short blue arrow labeled "WATER IN" or "INLET" with a callout line pointing to the inlet connection point on the cistern/tank
  b) TRAP PATH ({trap_type}): Highlight the trap pipe path in a bold blue color, thick line showing:
      • For "S-Trap": The drain exits the bottom of the bowl, curves DOWN in an S-shape (first curving backward then forward), and exits DOWNWARD through the floor. The floor line is clearly shown. The S-curve is labeled "S-TRAP" with a callout arrow.
      • For "P-Trap": The drain exits the bottom of the bowl, curves and exits HORIZONTALLY through the back wall (shown on the left side). The wall line is clearly shown. Labeled "P-TRAP".
      • For "Both S & P-Trap": Show BOTH paths — S-trap in blue going down, P-trap in teal going sideways — both emerging from the bowl base, with a junction labeled "UNIVERSAL TRAP"
  c) WATER EXIT POINT: At the very end of the trap path (where pipe meets floor or wall), show a clearly labeled callout: "WATER EXIT" or "OUTLET" with a small circle marking the outlet center
  d) WATER SEAL: Inside the trap curve, show translucent blue water representing the water seal — label it "WATER SEAL" in small italic text

CALLOUT DIMENSIONS (radiating from the diagram):
  1. ROUGH-IN: A horizontal double-headed arrow at floor level, measuring from the finished wall behind the toilet to the center of the outlet. Label: "{rough_in_inches} mm" in bold dark text + small gold uppercase label "ROUGH-IN" above the arrow. This arrow and measurement must be prominent and easy to read.
  2. FLOOR LINE: A horizontal reference line at floor level labeled "FLOOR LEVEL" on the right side, in small muted text
  3. OUTLET label: A callout line from the outlet point to the label "OUTLET" — shown separately from the rough-in arrow so both are clearly legible

RIGHT SIDE PANEL (right 35% of panel):
Three dark info cards stacked vertically, each with rounded corners, dark background, and a thin gold border:
  Card 1: A small floor-mounted installation icon + the text "{installation_type}" in white
  Card 2: An S-curve or P-curve icon matching the trap type + the text "{trap_type}" in white
  Card 3: A small ruler icon + the text "ROUGH-IN: {rough_in_inches} mm" in white

BOTTOM STRIP (bottom 15%): Clean white band, centered:
  The text: «Suitable for {installation_type} · {trap_type} outlet» in small muted grey text, centered

STYLE RULES:
  - The toilet exterior must look photorealistic (not a line drawing) — identical to IMAGE 1 (HERO)
  - The cutaway interior reveals internal plumbing with clear, clean diagram lines overlaid
  - The ROUGH-IN measurement and OUTLET label are the two most important callouts — make them unmistakably clear and well-separated
  - Trap pipe path (blue) should be the brightest colored element in the diagram
  - Floor tile texture must be very subtle — just enough to show floor context
  - Do NOT write font size numbers or CSS color codes as text in the image — only render actual label content
  - Amazon A+ quality, precision installation diagram with realistic product
  - 1:1 aspect ratio
""",
                    },

                    # ── SLOT 6: Ergonomic Comfort ──────────────────────────
                    {
                        "slot_id": "ergonomic_comfort",
                        "name": "Ergonomic Comfort",
                        "tagline": "Human silhouette showing seat height, posture & weight capacity",
                        "image_type": "infographic",
                        "is_hero": False,
                        "prompt_fragment": """\
INTENT: Communicate the ergonomic comfort of the {product_name} toilet — seat height, natural posture, and weight capacity. Use the actual photorealistic product from IMAGE 1 (HERO) as the visual base, with ergonomic callouts overlaid on top.

OVERALL LAYOUT: 1:1 square panel. Dark charcoal background (premium dark mode). The toilet product from IMAGE 1 is shown in the CENTER of the panel.

PRODUCT BASE: The toilet from IMAGE 1 (HERO) is shown in a clean 3/4 front-left view, photorealistic, centered slightly left in the panel. Soft warm rim lighting around the edges of the product to separate it from the dark background.

ERGONOMIC OVERLAYS on the product:
  A minimalist, abstract, gender-neutral human silhouette (warm-white outline only — no detail or face) is shown SEATED ON the actual product, in side profile. The silhouette is proportionally correct relative to the product. The seated posture shows: knees at natural 90°–100° bend, back upright with slight lumbar curve, feet flat on the floor.
  A vertical gold double-headed arrow runs along the left side of the combined figure, from floor to seat surface. The measurement «{seat_height} cm» is clearly labeled alongside the arrow in warm gold. A small gold uppercase label «SEAT HEIGHT» above the measurement.

FEATURE CALLOUT LINES (3 thin gold callout lines from the product):
  Callout 1: from the seat surface → label box: heading «COMFORT HEIGHT» / description «{seat_height} cm — optimal floor-to-seat elevation»
  Callout 2: from the seat/back profile area → label box: heading «NATURAL POSTURE» / description «Seat angle aligns spine naturally»
  Callout 3: from the base/bowl area → label box: heading «WEIGHT CAPACITY» / description «Certified for up to {weight_capacity_kg} kg»

BOTTOM STAT ROW (bottom 20%): Slightly lighter dark strip. Three stat tiles:
  Tile 1: Ruler icon + value «{seat_height} cm» in large thin gold + label «Seat Height» in small muted grey
  Tile 2: Weight icon + value «{weight_capacity_kg} kg» in large thin gold + label «Capacity» in small muted grey
  Tile 3: Star icon + word «Universal» in large thin gold + label «Comfort Design» in small muted grey

STYLE RULES:
  - Product MUST look photorealistic — identical to IMAGE 1 (HERO), NOT a line drawing or illustration
  - Human silhouette overlay must be minimal and abstract — just a warm-white outline, translucent
  - All callout lines: thin gold; label boxes: dark semi-transparent pills with white text
  - Full dark background throughout
  - Do NOT render any styling description notes as image text — only the «content words» for each label
  - Amazon A+ quality dark-mode panel
  - 1:1 aspect ratio
""",
                    },

                    # ── SLOT 7: Brand Hero Panel ───────────────────────────
                    {
                        "slot_id": "brand_hero",
                        "name": "Brand Lifestyle Hero",
                        "tagline": "Luxury lifestyle image with product name and 'Designed for Modern Living' tagline",
                        "image_type": "lifestyle",
                        "is_hero": False,
                        "prompt_fragment": """\
INTENT: Create a premium brand positioning image for the {product_name} toilet — luxury lifestyle photography style with product and tagline.

COMPOSITION & LAYOUT:
1:1 square lifestyle panel. Dark, moody, premium atmosphere — like a Villeroy & Boch or TOTO brand ad.

BACKGROUND:
  EXACTLY replicate the environment from IMAGE 1 (HERO IMAGE):
  - Same wall material, color, and texture
  - Same floor material and color
  - Same ambient lighting direction and warmth
  - Do NOT introduce any new room elements, props, plants, or accessories not in the HERO image
  - The environment should feel like the HERO image room but zoomed out slightly to reveal more wall/floor
  - Add very subtle atmospheric depth: gentle vignette at corners (darkening to 20% black), soft bokeh on background surfaces

PRODUCT PLACEMENT:
  - The toilet product, IDENTICAL in appearance to IMAGE 1 (HERO), is positioned slightly left of center, occupying approximately 50–60% of the frame height
  - View angle: 3/4 front-left perspective, slightly elevated camera angle
  - Studio-quality lighting on the product: key light from upper-left at 40°, soft fill from right, subtle rim light from behind-right
  - The product's ceramic surface is the {product_color} {material} shown in IMAGE 1 — pixel-for-pixel identical silhouette and finish

TEXT OVERLAY (right side of panel, vertically centered, right 35% of panel width):
  Right-aligned text block:
    Line 1: Brand/product name "{product_name}" in large thin warm-white text, generous letter-spacing
    Line 2: "— Designed for Modern Living" in smaller warm-gold italic text below
    Line 3: "{material} · {product_color}" in very small uppercase warm-white text at reduced opacity
  A thin gold horizontal rule between Line 1 and Line 2.

STYLE RULES:
  - Premium dark-luxury aesthetic — overall image should evoke a 5-star hotel bathroom
  - Product is the hero — text is a supporting overlay only
  - Absolutely NO logos, watermarks, website URLs, price text, or QR codes
  - Lighting on product must be warm and flattering — not harsh studio white
  - Do NOT write out font size numbers, hex color codes, or CSS specs in the image — only render the actual text content
  - CRITICAL: Do NOT copy any text, logos, or layout from competitor images — this is original brand content
  - Amazon A+ lifestyle banner quality
  - 1:1 aspect ratio
""",
                    },

                    # ── SLOT 8: Quality & Manufacturing ───────────────────
                    {
                        "slot_id": "quality_manufacturing",
                        "name": "Quality & Manufacturing",
                        "tagline": "Dark kiln-glow panel — firing temp, warranties, 4 quality test icons",
                        "image_type": "lifestyle",
                        "is_hero": False,
                        "prompt_fragment": """\
INTENT: Showcase the manufacturing quality, firing technology, and durability of the {product_name} ceramic toilet.

OVERALL LAYOUT: 1:1 square premium panel. Near-black full-panel background.

TOP SECTION (top 30%): Dramatic atmospheric visual:
  An abstract artistic representation of a ceramic kiln firing: glowing amber-orange-gold light radiating from the center (like peering into an industrial kiln). The heat glow is a soft circular radial effect — deep orange at the core gradually fading through amber and warm gold into the dark background. This glow is the only light source in the section. Centered, roughly half the panel width in diameter.

CENTER SECTION (middle 45%): Two information columns side by side on a near-black background:

  LEFT COLUMN (left half): Large stat block:
    - The value "{firing_temp_c}°C" displayed in enormous, ultra-thin warm gold lettering — this is the hero number, make it visually dominant
    - Below it, label "FIRING TEMPERATURE" in small uppercase warm-white text with generous letter-spacing
    - Below a thin gold separator line: the sentence "Superior vitrification for hardness and stain resistance" in small muted grey text

    Below this, two smaller stat blocks:
    - The value "{warranty_body_years} YEARS" in large thin gold lettering + label "BODY WARRANTY" in small uppercase warm-white text
    - The value "{material}" in medium thin warm-white text + label "PREMIUM MATERIAL" in tiny uppercase gold text

  RIGHT COLUMN (right half): Four quality testing icon cards arranged in a 2×2 grid:
    Each card is a very dark rounded rectangle with a slightly lighter border:
      Cell 1: A hammer/strength icon in gold outline + title "IMPACT RESISTANT" in tiny gold uppercase + description "Tested to {weight_capacity_kg} kg load" in tiny muted grey
      Cell 2: A water-drop icon in gold + title "STAIN RESISTANT" in tiny gold uppercase + description "Non-porous {glaze_type}" in tiny muted grey
      Cell 3: A thermometer icon in gold + title "THERMAL STABLE" in tiny gold uppercase + description "No crazing, no cracking" in tiny muted grey
      Cell 4: A shield/certified icon in gold + title "BIS CERTIFIED" in tiny gold uppercase + description "Quality Standard Tested" in tiny muted grey

BOTTOM SECTION (bottom 25%): Dark charcoal strip. Three inline stats in a row, separated by thin vertical gold lines:
  "FIRED AT {firing_temp_c}°C" · "{material} BODY" · "{warranty_body_years} YEAR GUARANTEE"
  All in small thin warm-white lettering.

STYLE RULES:
  - Dramatic dark industrial/manufacturing aesthetic — communicates quality through visual intensity
  - The kiln glow must feel atmospheric and real — not a cartoon circle
  - All text must be ultra-thin weight for premium luxury feel
  - Do NOT write out font size numbers, hex color codes, or CSS property values as image text — only render the actual content labels and stat values
  - Amazon A+ quality dark-mode feature panel
  - 1:1 aspect ratio
""",
                    },

                    # ── SLOT 9: Universal Comfort ──────────────────────────
                    {
                        "slot_id": "universal_comfort",
                        "name": "Universal Comfort",
                        "tagline": "Child / adult / elderly silhouettes with shared seat-height reference line",
                        "image_type": "infographic",
                        "is_hero": False,
                        "prompt_fragment": """\
INTENT: Show that the {product_name} toilet is designed for all users — children, adults, and elderly — highlighting universal accessibility and comfort.

OVERALL LAYOUT: 1:1 square infographic panel. Top 15% is a dark charcoal header strip; the remaining 85% is clean warm white.

HEADER (top 15%): Centered on dark strip:
  • Small gold uppercase label: "UNIVERSAL COMFORT"
  • Below it, medium thin warm-white text: "Designed for every member of the family"

MAIN AREA (middle 60%): Three equally-wide silhouette panels side by side:

  Panel 1 — CHILD (approx age 8–10):
    Minimalist, clean warm-white outline silhouette of a small child seated on a toilet (side profile). No detailed features — just a recognizable child scale.
    • A gold dashed horizontal seat-height reference line at the child's knee level
    • Small gold uppercase label below the silhouette: "CHILD"
    • Muted grey sub-label: "Low seat height for small users"

  Panel 2 — ADULT (25–40):
    Same minimal outline silhouette style, adult proportions, seated on the same toilet.
    • A gold solid horizontal reference line at the adult's knee height — this corresponds to "{seat_height} cm" and is the definitive seat height marker
    • Small gold uppercase label below: "ADULT"
    • Muted grey sub-label: "{seat_height} cm ergonomic seated height"

  Panel 3 — ELDERLY (60+):
    Same minimal outline, older-adult proportions, seated on the same toilet.
    • Same gold reference line continuing from Panel 2
    • A small accessibility icon (person with cane or wheelchair symbol) in gold, top-right of the panel
    • Small gold uppercase label below: "SENIOR"
    • Muted grey sub-label: "Comfortable height for easy sit-down"

  Between panels: thin vertical gold separator lines
  A single continuous gold horizontal reference line running across ALL THREE panels at the shared seat height — this is the key visual device tying all three panels together

BOTTOM SECTION (bottom 25%): Light grey strip. Three icon-badges in a row:
  Badge 1: Three-figures family icon + label "MULTI-USER DESIGN" in small dark uppercase
  Badge 2: Accessibility icon + label "ACCESSIBLE HEIGHT" in small dark uppercase + sub-value "{seat_height} cm" in gold
  Badge 3: Weight/capacity icon + label "{weight_capacity_kg} KG CAPACITY" in small dark uppercase

STYLE RULES:
  - Silhouettes must be very clean minimal outlines — not cartoons, not photographs
  - All three silhouettes must be proportionally accurate relative to each other and relative to the shared toilet silhouette
  - The continuous gold reference line is the key visual device — make it prominent and clearly continuous across all three panels
  - Warm, welcoming feel despite the minimal design
  - Do NOT write out font size numbers, hex color codes, or CSS property values as image text — only render the actual label content
  - Amazon A+ quality
  - 1:1 aspect ratio
""",
                    },

                    # ── SLOT 10: Feature Showcase (Cutaway) ────────────────
                    {
                        "slot_id": "feature_showcase",
                        "name": "Feature Showcase",
                        "tagline": "Cutaway 3D view with 5 callout arrows covering all key features",
                        "image_type": "feature",
                        "is_hero": False,
                        "prompt_fragment": """\
INTENT: Showcase all key features of the {product_name} toilet in one comprehensive annotated product image — the "all-in-one features overview" panel.

OVERALL LAYOUT: 1:1 square panel. Full dark charcoal background with a barely perceptible subtle texture.

HEADER (top 15%): Centered:
  • Small gold uppercase label: "KEY FEATURES"
  • Below it, medium thin warm-white text: "{product_name} · The Complete Package"
  • Thin gold separator line below text

CENTER DIAGRAM (middle 70%):
The toilet product in a 3/4 FRONT-LEFT VIEW — IDENTICAL in shape, color ({product_color}), and finish to IMAGE 1 (HERO IMAGE). Must be photorealistic, not a line drawing. The product sits in the center-left of the panel, with 5 callout annotations radiating outward to both sides.

5 FEATURE CALLOUT ANNOTATIONS:
Each callout is: a thin straight gold line from the product feature location → a small filled gold circle at the product contact point → the line extends to a small dark label box with gold border and white text inside.

  1. FLUSH SYSTEM (callout from cistern/tank area):
     Label box content:
       Title line: "{flush_type} FLUSH" in small gold uppercase
       Detail line: "{flush_mode} · {flush_volume}" in small warm-white thin text

  2. GLAZE & SURFACE (callout from bowl rim area):
     Label box content:
       Title: "{glaze_type}" in small gold uppercase
       Detail: derive a one-line benefit from {glaze_type}: if Anti-Bacterial then "Kills germs, prevents stains"; if Nano then "Ultra-smooth nano coating, self-cleaning"; if Standard then "Smooth vitrified surface"

  3. SEAT CLOSE (callout from seat hinge area):
     Label box content:
       Title: "{seat_close_type} SEAT" in small gold uppercase
       Detail: "{seat_material} · " followed by: if {seat_close_type} is Soft Close then "Silent close technology"; if Standard Close then "Reliable standard hinge" — in small warm-white thin text

  4. TRAP & ROUGH-IN (callout from the base/outlet area):
     Label box content:
       Title: "{trap_type}" in small gold uppercase
       Detail: "{rough_in_inches} mm rough-in · {installation_type}" in small warm-white thin text

  5. SKIRTED BASE DESIGN (callout from lower body/skirted panel area):
     Label box content:
       Title: "{base_style} DESIGN" in small gold uppercase
       Detail: "Concealed plumbing · Easy cleaning" in small warm-white thin text

CALLOUT PLACEMENT: Distribute callouts so they don't overlap. Approximately 2 on the left side, 3 on the right, or balanced visually. All label boxes must be clearly legible against the dark background.

BOTTOM STRIP (bottom 15%): Slightly lighter dark strip. Three badge pills in a row:
  • "{warranty_body_years} YR WARRANTY" — thin gold-border pill, white text
  • "BIS CERTIFIED" — thin gold-border pill, white text
  • "{water_rating}" — thin gold-border pill, white text
  All badges in small uppercase white text on dark background with thin gold border.

STYLE RULES:
  - Product must look photorealistic and IDENTICAL to IMAGE 1 (HERO) — same color, shape, gloss level
  - Dark luxury feel — product and callout labels must be crystal clear and legible
  - Callout lines must look elegant, not cluttered — clean and evenly spaced
  - Do NOT write out font size numbers, hex color codes, or CSS specs as visible image text — only render the actual label content
  - Do NOT add any elements not specified: no extra icons, no floor/walls, no price tags
  - This is the signature "all features" panel — it must look premium and complete
  - Amazon A+ quality
  - 1:1 aspect ratio
""",
                    },

                ],  # end catalog_slots
            },  # end toilet
        },  # end bathroom_products.products
    },  # end bathroom_products
}  # end PRODUCT_CATALOG
