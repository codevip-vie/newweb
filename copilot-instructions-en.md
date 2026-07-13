# 🔒 MANDATORY RULESET FOR GITHUB COPILOT
> This is not a suggestion. This is a HARD CONSTRAINT. Violating any rule below means the code is considered FAILED and must be rewritten.

---

## ARTICLE 0 — SUPREME PRINCIPLES
1. **DO NOT infer requirements on your own.** If a request is ambiguous, ask for clarification or explicitly state your assumption before coding. Never "guess" and code blindly.
2. **DO NOT add features outside the requested scope** (no scope creep). Only implement exactly what was asked — no unsolicited "creative additions."
3. **DO NOT delete, rename, or refactor unrelated code** unless explicitly permitted for the current task.
4. **Every change must be traceable**: briefly explain *why* something changed, not just *what* changed.
5. If you are not 100% certain about an API, library, or behavior — **do not hallucinate**. Verify against official documentation or use a pattern you are certain is correct.

---

## ARTICLE 1 — REQUIREMENT-ADHERENCE RULES (ANTI SCOPE-DRIFT)
- [ ] Before coding: restate the requirements as a short checklist in a comment at the top of the file/PR.
- [ ] Every implemented feature must map directly to at least one line in the requirement checklist.
- [ ] If the requirement is missing information (e.g., missing edge case, missing data format), **stop and ask** — do not invent assumed inputs/outputs.
- [ ] Do not code "just in case for later" (speculative generality / over-engineering) unless explicitly requested.
- [ ] Do not change existing architecture, libraries, or naming conventions already established in the project unless explicitly instructed.
- [ ] When fixing a bug: fix only the actual root cause — do not "fix-spread" into unrelated areas.

---

## ARTICLE 2 — GENERAL CODE STANDARDS (MANDATORY FOR ALL LANGUAGES)
1. **Readability first, cleverness second.** Do not write "clever" code that sacrifices clarity to look concise.
2. **Clear, consistent naming**: variables/functions/classes must express their purpose — no cryptic abbreviations (`x`, `tmp`, `data2`, etc.).
3. **No magic numbers/strings.** Every fixed value must be a named constant.
4. **Single Responsibility**: each function does exactly one thing. Functions longer than ~40–50 lines should be reconsidered for splitting.
5. **DRY, but not to excess**: don't copy-paste logic, but also don't abstract prematurely for something used only once.
6. **Comments explain "why," not "what"** (the code itself should already say what it does).
7. **No dead code left behind**, no leftover debug `console.log`/`print` statements.
8. **Type safety is mandatory**: use TypeScript strict mode / Python type hints / full generics. `any` (TS) is forbidden unless truly unavoidable, with a comment explaining why.
9. **Format code according to the project's linter/formatter** (ESLint, Prettier, Black, gofmt, etc.) — do not impose your own style.
10. **Do not submit code that hasn't been tested at least manually/via logs.**

---

## ARTICLE 3 — BACKEND STANDARDS (ZERO BUGS, ZERO SECURITY HOLES)
### 3.1 Error Handling & Validation
- Every input from the client **MUST be validated** (schema validation: zod/yup/joi/pydantic, etc.) — never trust incoming data.
- Every async/IO function **MUST have try-catch** or an equivalent error boundary — never let an error throw uncontrolled.
- Return errors to the client in a consistent standard format: `{ success, error: { code, message } }` (or per project convention).
- Never expose stack traces or internal system details in a production response.
- Log errors fully on the server (with context: request ID, user ID if available) but NEVER log sensitive data (passwords, tokens, PII).

### 3.2 Security (mandatory, non-negotiable)
- Never hardcode secrets/API keys/connection strings in code — always use environment variables (`.env`).
- All DB queries must use parameterized queries / an ORM — string concatenation that enables SQL injection is forbidden.
- Any input rendered back to the UI must be escaped/sanitized — prevent XSS.
- Apply rate limiting to public/sensitive endpoints (login, register, forgot-password).
- Passwords must be hashed with bcrypt/argon2 — never store plaintext.
- Check authorization (not just authentication) on EVERY endpoint — a user may only act on their own resources unless granted admin rights.

### 3.3 Database & Performance
- Transactions are mandatory for write operations spanning multiple related tables (ensures data integrity — ACID).
- No N+1 queries — use proper eager loading/joins.
- Index columns that are frequently filtered/sorted.
- Migrations must be rollback-able.

### 3.4 API Design
- REST/GraphQL endpoints must be named consistently and correctly (plural nouns, semantically correct HTTP methods: GET has no side effects, POST creates, PUT/PATCH updates, DELETE removes).
- Version the API when introducing breaking changes (`/api/v1/...`).
- Responses must always carry the correct HTTP status code (200, 201, 400, 401, 403, 404, 409, 422, 500, etc.).
- Pagination is mandatory for endpoints returning large lists.

---

## ARTICLE 4 — UX/UI STANDARDS: "AI SLOP" IS BANNED
> "AI Slop UI" = generic, soulless interfaces that look like default bootstrap demos — lacking detail, lacking personality. **ABSOLUTELY FORBIDDEN.**

### 4.1 The following are banned
- ❌ No default "AI generic" purple-blue gradients without a genuine design rationale.
- ❌ No cookie-cutter card/grid layouts lacking visual hierarchy.
- ❌ No icons/emoji standing in for real content (e.g., using 🚀 instead of meaningful text).
- ❌ No single shared value for all spacing/font-size with no underlying system (no spacing scale/type scale).
- ❌ No missing states: loading state, empty state, error state — any component displaying dynamic data MUST handle all three.
- ❌ No buttons/links without clear hover, active, disabled, and focus states.

### 4.2 The following are mandatory
- ✅ **Consistent design tokens**: color palette, spacing scale (4/8px system), typography scale — defined once, used everywhere.
- ✅ **Clear visual hierarchy**: users should immediately see the primary action (primary CTA) versus secondary ones.
- ✅ **Accessibility (a11y) is mandatory**: alt text for images, contrast ratio ≥ 4.5:1 for text, keyboard navigation, aria-labels for interactive elements without visible text.
- ✅ **Truly responsive** (not just resizing — layout must adapt sensibly across mobile/tablet/desktop).
- ✅ **Purposeful micro-interactions**: animations/transitions must serve a UX reason (action feedback) — no gratuitous animation that distracts.
- ✅ **Standard form UX**: real-time validation, clear error messages right next to the field, preserve entered data on failed submission.
- ✅ **Consistency**: the same type of action must always use the same UI pattern app-wide (e.g., a "Delete" button can't be red in one place and gray in another).
- ✅ Placeholder/dummy content must be contextually realistic — no "Lorem ipsum" or "asdasd" in a real product.

---

## ARTICLE 5 — MANDATORY SELF-CHECK BEFORE SUBMITTING ANY CODE
Before considering any code complete, you MUST be able to answer "YES" to all of the following:
1. [ ] Does the code match the requirements exactly — no more, no less?
2. [ ] Are all edge cases handled (empty input, null, undefined, negative numbers, empty arrays, timeouts, network failure)?
3. [ ] Is there try-catch / error handling at every point that could fail?
4. [ ] Are there any security holes (injection, XSS, missing authorization)?
5. [ ] Are types accurate, with no careless `any`?
6. [ ] Does the UI handle loading/empty/error states?
7. [ ] Does the code follow the project's existing conventions/style?
8. [ ] Can you explain exactly what every line does and why it's needed?

If the answer to any of these is "NO" → the task is **not considered complete**; fix it before reporting the work as done.

---

## ARTICLE 6 — COMMUNICATION RULES (WHEN COPILOT PROPOSES CODE)
- If a request is unclear: ask a specific clarifying question — do not decide on the user's behalf.
- If multiple implementation approaches exist: briefly state the trade-offs — do not default to the "fancier" option just to seem impressive.
- Do not add new libraries/dependencies unless truly necessary — if one is needed, state the reason clearly.
- Do not write bloated, redundant code to "look like more effort was put in" — the simpler the code while still being correct, the better.

---

**Final reminder: Code doesn't just need to run — it must be CORRECT, SECURE, MAINTAINABLE, and match EXACTLY what was requested. Nothing more, nothing less.**
