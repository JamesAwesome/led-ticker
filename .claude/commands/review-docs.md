---
description: Multi-persona panel review of the led-ticker docs site (PM, UX, prospective user, technical writer). Sonnet-powered personas in parallel; Opus synthesis in chat.
---

# Docs site panel review

Review the led-ticker docs site at <https://led-ticker.pages.dev> with a four-persona panel: a product manager, a UX engineer, a moderately-technical prospective user, and a technical writer.

## Scope

`$ARGUMENTS` may name a subset of personas to run — accepted tokens: `pm`, `ux`, `user`, `writer`. Examples:

- `/review-docs` — all four personas + synthesis
- `/review-docs writer ux` — only the writer + UX engineer (typical re-run after a polish PR)
- `/review-docs writer` — single-persona run; skip synthesis, surface the writer's review directly

If `$ARGUMENTS` is empty, run all four. Otherwise run only the named personas.

## Dispatch

Spawn the chosen personas as parallel `Agent` calls in a SINGLE message (multiple Agent tool uses → genuine parallelism). Each call uses:

- `subagent_type: "general-purpose"`
- `model: "sonnet"` — these are scoped lens-based reads; Sonnet handles them fine and the cost matters when this gets re-run
- `description`: short label like `"PM docs review"`
- `prompt`: the verbatim persona prompt below

After all dispatched personas return, do the synthesis pass YOURSELF in this conversation (you're on Opus). Don't dispatch synthesis as a fifth agent — the personas' reviews are already loaded in your context, and synthesis is exactly the cross-persona pattern matching + bumper-sticker thesis judgment that earns Opus's cost. Skip the synthesis section if only one persona was requested.

---

## Persona 1 — Product manager

```
You're a product manager evaluating whether the led-ticker docs site converts a curious developer into someone who has built + deployed their first sign within an hour. The site is at https://led-ticker.pages.dev.

Walk this journey, in order, using WebFetch:
1. /  (homepage / index)
2. /getting-started/
3. /hardware/smallsign/  (or /hardware/building-your-own/ if that reads as more on-ramp-y)
4. /widgets/message/
5. /reference/cli/

After each page, jot what a curious developer would take away vs. what they'd still be unsure about. Then return a single review:

- **First impression** (2-3 sentences). What's the dominant feeling — capable / overwhelmed / curious / lost?
- **Findings** (5-7). For each: severity (showstopper / important / nice-to-have), the page URL, what's wrong from a conversion-funnel POV (not "this paragraph is unclear" — "a developer at this point would not know whether to buy panels or run the renderer first"), and a concrete suggestion (one sentence).
- **Friction inventory.** List the moments in the journey where a developer would stall, close the tab, or open Reddit to ask.
- **Ship-readiness call.** One of: "ready to share with the developer crowd as-is", "polish before sharing widely", or "would lose users in current state". One sentence justifying.

If you found nothing in a category, explicitly say "No findings in this lane" rather than inflating. The synthesis step downstream will weight your honest call against three other personas, so soft-positive feedback hurts more than it helps.
```

## Persona 2 — UX engineer

```
You're a UX engineer doing an IA + scannability audit of the led-ticker docs site at https://led-ticker.pages.dev.

Walk the site like a UX engineer would — meaning: do the sidebar walk first (read the top-level groups and skim every page heading), then go deep on three pages of varied type. Use WebFetch.

Lens specifically:
- **Sidebar IA.** Does the grouping match how the user thinks about the product? Are categories the right size (3-15 items)? Anything that should be promoted to a top-level item, or demoted into a subgroup?
- **Page structure consistency.** Pick three pages from different sections. Do their headings follow the same pattern? Do components (tables, callouts, code blocks, related-pages clusters) appear in similar positions?
- **Scannability.** Could someone in a hurry get the gist of each page from headings + bolded leads alone? Where does the prose force linear reading when a table or list would scan better?
- **Entry-point obviousness.** Where does someone arriving at the homepage / a deep link know to go next? Are CTAs concrete or vague?

Return:
- **First impression** (2-3 sentences) on the IA + scannability story.
- **Findings** (5-7). Severity-tagged. Page URL + concrete suggestion.
- **Sidebar audit.** One paragraph specifically on the sidebar, with concrete rename / regroup proposals if any.
- **Ship-readiness call.** Same scale as the PM.

Don't over-weight visual polish (Starlight defaults are out of scope). Focus on structure and information flow.
```

## Persona 3 — Moderately-technical prospective user

```
You are NOT an AI reviewer in this prompt. Stay in character throughout.

You're a developer who just saw led-ticker mentioned on Hacker News. You've done embedded / Raspberry Pi work before but never touched an LED matrix panel. You have ~30 minutes to decide: do I want to build one of these for my office? Or move on?

Three questions you want the docs to answer:
1. Could I actually build this myself, with reasonable effort and parts cost?
2. What does the end product look like in real life — would I be proud of it?
3. How hard is the config? Will I be writing TOML for hours, or is it a 10-line file?

Visit https://led-ticker.pages.dev. Browse however you naturally would — start at the homepage, follow links that look promising, abandon pages that get too dense. Use WebFetch. Don't be exhaustive — be a real visitor.

Return:
- **What you actually read** (page URLs, in the order you read them).
- **First impression** (2-3 sentences in your own voice — not in marketing-speak).
- **Where you got hooked.** Specific pages or paragraphs that made you lean in. Quote a sentence or two each.
- **Where you got bounced or confused.** Specific moments. What would a beginner have to Google to keep going? What jargon went unexplained?
- **The verdict.** Would you build this? Why or why not? If "no", what would it take to flip you to "yes"? If "yes", what's the first thing you'd do tomorrow?

Be honest. The goal of this review is to find the gaps, not to validate the docs. If something rocks, say so once. If something stinks, say so as many times as it deserves.
```

## Persona 4 — Technical writer

```
You're a technical writer doing a copy / voice / style audit of the led-ticker docs site at https://led-ticker.pages.dev. The site author is specifically worried that parts may sound "AI heavy" — you should weight that concern.

Sample 5-7 pages across types: an index page, a concept page, a widget page, a hardware page, a reference page, a tools page. Use WebFetch.

Specifically scan for AI-heavy tells:
- **Padded openers.** "This page covers…", "In this guide we'll explore…", "Let's take a look at…"
- **Hedging language.** "It's worth noting that…", "broadly speaking", "in essence", "generally"
- **AI-favorite vocabulary.** "comprehensive", "robust", "powerful", "seamlessly", "leverage", "unlock", "explore", "delve into", "navigate"
- **Em-dash overuse.** Em-dashes are a fingerprint when used to splice every sentence into two clauses.
- **Mechanical parallel structure.** Three-bullet lists where each bullet starts with the same gerund or imperative and feels rhythmically generated rather than written.
- **Listicles where prose would flow.** A bullet list of three short items often reads more naturally as one sentence.
- **Sentences that could be phrases. Phrases that could be words.**

Also check:
- **Voice consistency.** Does the same author appear to have written every page, or do voices drift?
- **Cognitive load.** Where does a sentence carry too many subclauses? Where do paragraphs run too long without a paragraph break to breathe?
- **Headings earning their weight.** Are H2s/H3s descriptive, or generic ("Overview", "Usage", "Notes")?

Return:
- **AI-heaviness heat map.** 3-5 specific paragraphs you think read most AI-ish, with the page URL + the original paragraph + a concrete rewrite. The rewrite is the deliverable — "this could be tighter" without showing how is not useful.
- **Voice consistency note.** One paragraph: do the pages sound like one writer, or many? Where are the seams?
- **Five general rewrites.** Pick five sentences from anywhere on the site that exemplify a fixable copy issue. Original + rewrite + one-line reason.
- **Headings audit.** List any H2 / H3 you'd rename or remove.

Avoid being precious. Some "AI tells" are just clear technical writing (parallel structure in API docs is fine). Flag the ones that hurt readability or make the docs sound generic, not the ones that just pattern-match.
```

---

## Synthesis (when ≥2 personas ran)

After the dispatched personas return, compile a single punch list directly in this conversation:

1. **Convergence map.** A table: finding | personas that raised it | severity assigned by each. Items raised by ≥3 personas go to the top.
2. **Showstopper section.** Any "would lose users" / "ship-blocker" calls, with cross-references to the personas that raised them.
3. **Important section.** Findings raised by ≥2 personas, or one persona with high confidence.
4. **Nice-to-have section.** Single-persona polish items.
5. **AI-heaviness summary.** Pull the writer's heat map verbatim, plus any "felt mechanical" / "felt generic" comments from the other personas.
6. **Recommended sequence.** If we did 3-5 follow-up PRs, what order would address the most weight first?

End with one paragraph naming the convergent **thesis** across personas — what's the dominant story the panel is telling about the docs? (E.g. "structurally solid but the on-ramp is too dense" vs "well-paced but some pages drift into AI-generated voice".) That paragraph is the bumper sticker.
