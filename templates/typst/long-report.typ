// ─────────────────────────────────────────────────────────────────────────────
// long-report.typ — Professional client report template (10–40+ pages)
// Vizier Ultimate — Typst 0.14.2, no external packages
//
// Usage: callers append body content after this preamble.
//   = Section Title
//   == Sub-section
//   === Detail
//   Plain paragraphs, tables, figures, etc.
// ─────────────────────────────────────────────────────────────────────────────

// ── Brand inputs ─────────────────────────────────────────────────────────────
#let primary    = rgb(sys.inputs.at("primary_color",   default: "#1A1A2E"))
#let secondary  = rgb(sys.inputs.at("secondary_color", default: "#F0F0F5"))
#let accent     = rgb(sys.inputs.at("accent_color",    default: "#2563EB"))
#let heading-font  = sys.inputs.at("headline_font", default: "Arial")
#let body-font     = sys.inputs.at("body_font",     default: "Libertinus Serif")
#let report-title  = sys.inputs.at("title",         default: "Report")
#let report-subtitle = sys.inputs.at("subtitle",    default: "")
#let report-author = sys.inputs.at("author",        default: "")
#let report-date   = sys.inputs.at("date",          default: "")
#let report-client = sys.inputs.at("client_name",   default: "")

// ── Page setup ───────────────────────────────────────────────────────────────
#set page(
  paper: "a4",
  margin: (rest: 2.5cm),
  header: context {
    // Show header rule only after the first two pages (cover + TOC)
    if counter(page).get().first() > 2 [
      #line(length: 100%, stroke: 0.5pt + luma(180))
    ]
  },
  footer: context [
    #align(right)[
      #text(size: 9pt, fill: luma(120))[
        #counter(page).display("1")
      ]
    ]
  ],
)

// ── Base typography ───────────────────────────────────────────────────────────
#set text(
  font: body-font,
  size: 11pt,
  fill: luma(30),
)
#set par(
  leading: 0.65em,
  spacing: 1.4em,
)

// ── Heading numbering ─────────────────────────────────────────────────────────
#set heading(numbering: "1.1")

// ── Heading show rules ────────────────────────────────────────────────────────
#show heading.where(level: 1): it => {
  v(1.8em)
  text(
    font: heading-font,
    size: 18pt,
    weight: "bold",
    fill: primary,
  )[#it]
  v(0.5em)
}

#show heading.where(level: 2): it => {
  v(1.2em)
  text(
    font: heading-font,
    size: 14pt,
    weight: "bold",
    fill: primary,
  )[#it]
  v(0.3em)
}

#show heading.where(level: 3): it => {
  v(0.8em)
  text(
    font: heading-font,
    size: 12pt,
    weight: "bold",
    fill: primary,
  )[#it]
  v(0.2em)
}

// ── Table styling ─────────────────────────────────────────────────────────────
#set table(
  stroke: 0.5pt + luma(200),
  inset: 8pt,
)
// Header row: white bold text on primary background
#show table.cell.where(y: 0): set text(fill: white, weight: "bold")
#show table.cell.where(y: 0): set block(fill: primary)

// Even data rows: light secondary background (rows 2, 4, 6 … → y = 2, 4, 6)
#show table.cell: it => {
  if it.y > 0 and calc.even(it.y) {
    set block(fill: secondary)
    it
  } else {
    it
  }
}

// ── Figure captions ───────────────────────────────────────────────────────────
#set figure(supplement: "Figure")

// ── Links ─────────────────────────────────────────────────────────────────────
#show link: set text(fill: accent)

// ═════════════════════════════════════════════════════════════════════════════
// COVER PAGE
// ═════════════════════════════════════════════════════════════════════════════
#page(
  margin: (rest: 0pt),
  header: none,
  footer: none,
)[
  // Full-width primary colour bar at top
  #rect(
    width: 100%,
    height: 6cm,
    fill: primary,
  )

  // Content block below the bar
  #pad(left: 2.5cm, right: 2.5cm, top: 1.5cm, bottom: 2.5cm)[
    // Title
    #text(
      font: heading-font,
      size: 28pt,
      weight: "bold",
      fill: primary,
    )[#report-title]

    // Subtitle
    #if report-subtitle != "" [
      #v(0.4em)
      #text(
        font: heading-font,
        size: 16pt,
        fill: luma(60),
      )[#report-subtitle]
    ]

    #v(1.5em)
    #line(length: 8cm, stroke: 1.5pt + accent)
    #v(1.5em)

    // Client
    #if report-client != "" [
      #text(size: 12pt, fill: luma(40))[*Prepared for:* #report-client]
      #v(0.4em)
    ]

    // Author
    #if report-author != "" [
      #text(size: 12pt, fill: luma(40))[*Prepared by:* #report-author]
      #v(0.4em)
    ]

    // Date
    #if report-date != "" [
      #text(size: 12pt, fill: luma(40))[*Date:* #report-date]
    ]
  ]
]

// ═════════════════════════════════════════════════════════════════════════════
// TABLE OF CONTENTS
// ═════════════════════════════════════════════════════════════════════════════
#page[
  #text(
    font: heading-font,
    size: 18pt,
    weight: "bold",
    fill: primary,
  )[Contents]
  #v(0.8em)
  #line(length: 100%, stroke: 0.5pt + luma(200))
  #v(0.6em)
  #outline(
    indent: 1.5em,
    depth: 3,
  )
]
