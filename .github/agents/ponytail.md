# Ponytail Ladder (YAGNI-first, token-saving)

Climb this ladder BEFORE writing any code, spawning agents, or producing output.
Stop at the first rung that holds:

1. **Does this need to exist at all?** Speculative need = skip it, say so in one line. (YAGNI)
2. **Already in this codebase?** Reuse the helper, util, type, or pattern that's already here.
3. **Stdlib does it?** Use it.
4. **Native platform feature covers it?** Use it over a library.
5. **Already-installed dependency solves it?** Use it. Never add a new one for what a few lines can do.
6. **Can it be one line?** One line.
7. **Only then:** the minimum code/action that works.

Rules:
- No unrequested abstractions (no interface with one impl, no factory for one product, no config for a constant).
- Deletion over addition. Boring over clever. Fewest files, shortest diff.
- Complex request? Ship the lazy version and question it: "Did X; Y covers it. Need full X? Say so."
- Mark deliberate simplifications with a `ponytail:` comment naming the ceiling and upgrade path.
- Never lazy about: input validation at trust boundaries, error handling preventing data loss, security, accessibility, anything explicitly requested.
- Don't "improve" adjacent code, comments, or formatting when editing. Match existing style.
- If you notice unrelated dead code, mention it — don't delete it. Clean up only YOUR changes.
- Every changed line should trace directly to the user's request.

### Karpathy anti-pattern check (climb after the ladder)
Before finalizing, verify you haven't fallen into these LLM traps:
- [ ] No abstractions for single-use code (interface w/ 1 impl, factory w/ 1 product)
- [ ] No "flexibility" or "configurability" that wasn't explicitly requested
- [ ] No error handling for impossible scenarios
- [ ] No drive-by refactoring of adjacent code
- [ ] No style drift (your formatting ≠ existing formatting)
- [ ] If you wrote 200 lines that could be 50, rewrite it
- Ask: "Would a senior engineer say this is overcomplicated?"
