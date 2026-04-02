// ── Brand inputs ─────────────────────────────────────────────────────────────
#let primary      = rgb(sys.inputs.at("primary_color",  default: "#1A1A2E"))
#let secondary    = rgb(sys.inputs.at("secondary_color", default: "#F0F0F5"))
#let accent       = rgb(sys.inputs.at("accent_color",   default: "#2563EB"))
#let heading-font = sys.inputs.at("headline_font", default: "Georgia")
#let body-font    = sys.inputs.at("body_font",     default: "Libertinus Serif")
#let book-title   = sys.inputs.at("title",    default: "Untitled")
#let book-subtitle = sys.inputs.at("subtitle", default: "")
#let book-author  = sys.inputs.at("author",   default: "")
#let book-date    = sys.inputs.at("date",     default: "")

// ── Chapter title state (for recto running header, if desired) ────────────────
#let chapter-title = state("chapter-title", "")

// ── Page setup ───────────────────────────────────────────────────────────────
#set page(
  width: 6in,
  height: 9in,
  margin: (inside: 2cm, outside: 1.5cm, top: 2cm, bottom: 1.5cm),
  header: context {
    let page-num = counter(page).get().first()
    if page-num > 2 {
      if calc.even(page-num) [
        // Verso (even): book title, left-aligned
        #set text(size: 9pt, fill: primary.lighten(30%))
        #book-title
        #line(length: 100%, stroke: 0.4pt + primary.lighten(60%))
      ] else [
        // Recto (odd): blank header
        #line(length: 100%, stroke: 0.4pt + primary.lighten(60%))
      ]
    }
  },
  footer: context {
    let page-num = counter(page).get().first()
    if page-num > 2 {
      set text(size: 9pt, fill: primary.lighten(30%))
      align(center)[#counter(page).display("1")]
    }
  },
  numbering: "1",
)

// ── Base typography ───────────────────────────────────────────────────────────
#set text(font: body-font, size: 11pt, fill: rgb("#1C1C1C"))
#set par(leading: 0.75em, spacing: 1.5em, first-line-indent: 1.5em)

// ── Heading styles ────────────────────────────────────────────────────────────
#show heading.where(level: 1): it => {
  pagebreak(to: "odd", weak: true)
  chapter-title.update(it.body)
  v(3em)
  set text(font: heading-font, size: 24pt, fill: primary, weight: "bold")
  block(width: 100%)[
    #it.body
    #v(0.3em)
    #line(length: 40%, stroke: 1.5pt + accent)
  ]
  v(1.5em)
}

#show heading.where(level: 2): it => {
  v(1.2em)
  set text(font: heading-font, size: 18pt, fill: primary, weight: "semibold")
  block[#it.body]
  v(0.6em)
}

#show heading.where(level: 3): it => {
  v(0.8em)
  set text(font: heading-font, size: 14pt, fill: primary, weight: "medium")
  block[#it.body]
  v(0.4em)
}

// ── Links ─────────────────────────────────────────────────────────────────────
#show link: it => {
  set text(fill: accent)
  underline(it)
}

// ── Title page ───────────────────────────────────────────────────────────────
#page(
  width: 6in,
  height: 9in,
  margin: (inside: 2cm, outside: 1.5cm, top: 2cm, bottom: 1.5cm),
  header: none,
  footer: none,
)[
  #align(center + horizon)[
    #text(font: heading-font, size: 32pt, fill: primary, weight: "bold")[#book-title]
    #if book-subtitle != "" {
      v(0.6em)
      text(font: heading-font, size: 18pt, fill: primary.lighten(20%))[#book-subtitle]
    }
    #if book-author != "" {
      v(2em)
      text(font: body-font, size: 13pt)[#book-author]
    }
    #if book-date != "" {
      v(0.8em)
      text(font: body-font, size: 11pt, fill: rgb("#666666"))[#book-date]
    }
  ]
]

// ── Table of contents ─────────────────────────────────────────────────────────
#page(
  width: 6in,
  height: 9in,
  margin: (inside: 2cm, outside: 1.5cm, top: 2cm, bottom: 1.5cm),
  header: none,
  footer: none,
)[
  #set text(font: body-font, size: 11pt)
  #text(font: heading-font, size: 20pt, fill: primary, weight: "bold")[Contents]
  #v(1em)
  #outline(indent: 1.5em, depth: 2)
]

// ── Body begins here (callers append chapters below this line) ────────────────
