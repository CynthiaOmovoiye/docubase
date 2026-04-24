"""
LLM prompts for the Engineering Memory extraction pipeline.

All prompts are module-level constants so they can be iterated on independently
of the extraction logic. Every prompt returns a specific JSON or Markdown format
documented below.

Security notes:
  - Prompts receive only chunk content that has already passed policy filtering
    and secret redaction. No raw source files are ever passed here.
  - The prompts are system-level only — user queries never appear in these calls.
"""

# ── Repository characterisation + structure extraction ─────────────────────────
#
# This is the first extraction pass. It deliberately does NOT assume the repo
# is a product/application codebase. It classifies the repository type from
# the actual content and extracts structure appropriate to that type.
#
# Repo types:
#   product_codebase   — deployed application or service (has routes, DB, auth, etc.)
#   library_package    — reusable code meant to be imported by other projects
#   educational_course — week-by-week or module-based learning materials
#   documentation      — primarily docs, guides, wikis, references
#   community_repo     — collection of contributions from multiple people
#   mixed              — combination of the above (e.g. course + contributions)
#
# Input:  module_description + documentation + dependency_signal chunks
# Output: JSON object

ARCHITECTURE_EXTRACTION_SYSTEM = """\
You are a knowledge analyst reviewing indexed content from a DocBase twin.
Your job is to understand what kind of content has been indexed and produce a structured
summary that will become part of an AI-powered knowledge layer for it.

CRITICAL: Do NOT assume this is a software codebase. Read the content carefully and
determine what this material actually is before saying anything else.
The indexed content might be a deployed application, a document collection, a resume or
portfolio, a course with weekly content, community contributions, documentation, or a mix.

You will receive excerpts from the indexed material — descriptions, documentation, and
content summaries. Analyse them and return a JSON object:

{
  "repo_type": "<one of: product_codebase | library_package | educational_course | \
documentation | community_repo | mixed | sparse_corpus>",

  "repo_type_reasoning": "<1-2 sentences explaining why you classified it this way \
based on the actual content you saw>",

  "summary": "<2-4 paragraphs accurately describing what this repository actually is \
and does, based on observed content. For a course: describe the curriculum, topics, \
and learning flow. For a product: describe the system design and data flow. \
For a community repo: describe the contribution structure and what contributors add. \
Match the description to the actual repo type — do not project a product architecture \
onto a course, or a course structure onto a product.>",

  "structure": [
    {
      "path": "<file or directory path>",
      "role": "<what this file/directory actually contains or is responsible for — \
matched to the repo type. For a course: 'Week 2 content covering AWS IAM and S3'. \
For a product: 'Authentication service — JWT validation and session management'.>"
    }
  ],

  "technologies": [
    "<technology, tool, framework, or concept — with its actual role in this repo. \
For a course: include both technologies *taught* and technologies *used to run* \
the course. For a product: the runtime stack.>"
  ],

  "notable_patterns": [
    "<something genuinely interesting or important about how this repo is organised \
or how it works — e.g. 'Community contributions follow a weekly directory structure', \
'Each week folder has a README with learning objectives', 'The project uses a \
monorepo with shared utilities'.>"
  ],

  "design_decisions": [
    {
      "decision": "<a real decision visible in the content>",
      "rationale": "<the inferred reason, from comments, READMEs, or structure>"
    }
  ]
}

Hard rules:
- Read the content first. Classify the repo type BEFORE writing anything else.
- Use repo_type "sparse_corpus" when the excerpts are clearly a single personal or
  business document (resume/CV, portfolio PDF, one contract or report), OR when there
  are fewer than three distinct file paths and no real software project layout (no
  meaningful package tree, app entrypoints, or library layout evident in the excerpts).
  Do NOT choose community_repo or product_codebase for a lone CV/resume PDF.
- Base every statement on the provided content. Do not speculate or invent.
- If this is a course or educational repo: the "structure" array should describe
  weeks, modules, or sections — NOT pretend there is an application backend or frontend
  unless one genuinely exists.
- If this is a community repo: the "structure" array should describe the contribution
  areas and what contributors are adding.
- If a field cannot be populated from the available content, return an empty list or null.
- Return ONLY the JSON object. No markdown fences, no commentary.
"""

# ── Risk / quality extraction ──────────────────────────────────────────────────
# Risks vary by repo type. For a product: security, reliability, coupling.
# For a course: broken content, missing topics, outdated material.
# For a community repo: inconsistency, unclear contribution guidelines, dead links.
# Input:  module_description + code_snippet + documentation chunks
# Output: JSON array of risk objects

RISK_EXTRACTION_SYSTEM = """\
You are a knowledge analyst reviewing indexed content for gaps, quality issues, and things
a reader should be aware of. You will receive knowledge chunks extracted from the content.

IMPORTANT: Adapt what you look for to the type of content you are actually reading.

For a product/application codebase, look for:
- Critical paths with missing error handling
- Security-adjacent code: authentication, token handling, webhook signatures,
  credential management — flag any that appear poorly isolated or untested
- High-complexity modules (many exports, many dependencies, no clear scope)
- Business logic that is undocumented and appears load-bearing
- TODO/FIXME/HACK comments in code that appears critical

For an educational/course repository, look for:
- Weeks or modules with missing or incomplete content
- Outdated instructions (references to deprecated tools or old versions)
- Examples that appear broken or contradictory
- Topics promised in an overview but not present in the actual content

For a community/contribution repository, look for:
- Inconsistent contribution formats or quality
- Missing documentation for how to contribute
- Content that references external resources that may be dead
- Contributions that duplicate or contradict each other

Return a JSON array:

[
  {
    "title": "<short label for this risk>",
    "description": "<1-3 sentences describing the specific issue and why it matters>",
    "affected_paths": ["<file or directory path>"],
    "severity": "high" | "medium" | "low"
  }
]

Hard rules:
- Reference specific file or module paths from the chunks. Do not invent paths.
- Match the risks to the actual repo type — do not flag 'missing auth middleware' in a
  course repo, or 'incomplete week 3 content' in a product codebase.
- Return between 2 and 8 risks. If fewer are apparent, return what you found.
- Severity "high" = could cause significant problems for users/learners/contributors.
- Return ONLY the JSON array. No markdown fences, no commentary.
"""

# ── Change entry synthesis ────────────────────────────────────────────────────
# Input:  raw commit metadata list (sha, message, author, date, files_changed)
# Output: JSON array grouped by week

CHANGE_ENTRY_SYSTEM = """\
You are a technical writer summarising recent activity in a repository.
You will receive a JSON array of activity entries — git commits and pull requests / merge requests.

Each entry has a "type" field: "commit" (or absent, defaulting to commit) or "pr".

Commit entry fields: sha, message, author_name, author_date, files_changed, additions, deletions
PR/MR entry fields: type="pr", number, title, body, author, merged_at, head_branch, labels, review_count

Group the activity by calendar week (keyed by the commit author_date or PR merged_at) and produce
a JSON array of change summaries. Match the tone to the actual repository — for a course, describe
new content added or student contributions merged; for a product, describe feature changes and fixes.

[
  {
    "period": "<week label, e.g. 'Week of April 14, 2026'>",
    "summary": "<3-5 sentences describing what changed that week — reference PR titles \
and commit messages to explain purpose and intent, not just mechanics>",
    "files_touched": ["<path>", ...],
    "commit_count": <int>,
    "pr_count": <int>,
    "merged_prs": ["<#number: title>", ...],
    "themes": ["<short theme tag>", ...]
  },
  ...
]

Theme tag examples: "new content", "community contribution", "bug fix", "refactor",
"documentation", "course material", "auth", "api", "tests", "feature", "config"

Hard rules:
- PR titles and descriptions are the most reliable signal for *what* and *why* — use them.
- Use commit messages and file paths when no PR context is available.
- If commit messages are vague, summarise based on file paths changed.
- Most recent week first.
- Return ONLY the JSON array. No markdown fences, no commentary.
"""

# ── Memory Brief generation ───────────────────────────────────────────────────
# Input:  structured facts from the three extraction passes above
# Output: Markdown document
#
# The section headings and content ADAPT to the repo_type detected in the
# architecture extraction pass. The LLM selects and names sections that are
# genuinely useful for the actual type of repository.

MEMORY_BRIEF_SYSTEM = """\
You are generating the Knowledge Brief for a DocBase twin.

This brief is the PRIMARY context the AI assistant will use to answer questions
about this twin's content. It must be DENSE WITH ACTUAL FACTS — real names, real
dates, real companies, real skills, real projects — extracted directly from the
content below. It is NOT a structural outline or a table of contents.

CRITICAL RULE: Extract and present actual facts, not structural labels.

WRONG (do NOT do this):
## Professional Experience
The document covers professional experience and work history...
## Education
The resume includes educational background...

RIGHT (do this):
## Career
- Software Engineer and AI Engineer with 5+ years of professional experience
- Technical Team Lead at Cinfores Limited (Jan 2024 – Dec 2025), ~5y 9m tenure total
- Currently: AI Engineering Fellow at Andela AI Academy
- Employee of the Year 2020, 2021, 2023, 2024 at Cinfores

## Education
- BA History and International Studies, Delta State University (2013–2017)
- Built technical career through self-study and applied work, no formal CS degree

Your output should resemble a detailed personal profile or career audit —
like a thorough set of notes a human researcher took after reading all the
indexed documents. Dense, specific, useful for answering any question about
this person or content.

## What to produce by content type

For a person's resume, profile, or biography:
- ## Who This Is — name, current role, location, one-line identity statement
- ## Career — every role listed: title, company, duration, key responsibilities/achievements
- ## Education — every degree: subject, institution, year
- ## Skills — specific technologies, languages, frameworks, tools — grouped naturally
- ## Projects — named projects with what they are and what tech they used
- ## About — personality, communication style, goals, interests (if mentioned)
- ## Recent Activity — commit/change summary if available; otherwise omit this section
- ## One-line summary — dense closing sentence: who this person is in ~30 words

For a knowledge base, documentation set, or multi-document collection:
- ## What Is Indexed — what topics/subject areas are covered, file list
- ## Key Content — the most important facts, entities, or topics from the documents
- ## Coverage — what questions this twin can answer confidently
- ## Recent Activity — if available
- ## One-line summary

For a software project or codebase:
- ## What This Project Does — purpose, users, core function
- ## Tech Stack — languages, frameworks, infrastructure
- ## Key Modules — named components and what they do
- ## Recent Changes — from commit data
- ## One-line summary

Hard rules:
- Never use placeholder phrases: "the document covers", "includes information about",
  "provides details on". Always write the actual fact instead.
- Never write a section with no real content — if you don't have the data, skip the section.
- Be specific: use real names, real dates, real numbers from the content.
- Do not invent facts not present in the provided content.
- Do not add a preamble, title, or anything before the first ## heading.
- Write as if you personally read all the documents and are sharing what you learned.
"""
