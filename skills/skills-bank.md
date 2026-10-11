---
id: skills-bank
name: skills-bank
type: skill
project: shared
tags: [meta, skills, prompts, bank, library]
description: "Search and use the user's Skills Bank — their library of skills, prompts, agents and rules — via the `bank` CLI. Use when the user types /skills-bank, says 'check my bank', 'do I have a skill/prompt for', 'use my … prompt', 'save this as a skill', 'add to the bank', or when a task likely matches something they've stored."
inputs: [request]
version: 1
---
## When to use
- The user invokes /skills-bank, with or without a request after it.
- The user asks whether they have a skill/prompt/agent for something, or to reuse one of theirs.
- The user asks to save, create or improve a skill or prompt.
- Do NOT use for general questions that don't involve their stored library.

## Inputs to collect first
- `request`: what they want to do. If /skills-bank is typed alone, run step 1 with no query and show the menu in step 6.

## Steps
1. **Find.** Run `bank search "<key words from the request>"`. If nothing matches, retry with 1–2 synonyms; if still nothing, say so and offer step 5.
2. **Pick.** Show at most 5 matches as `id — name (type, project)`. Choose the best one yourself when it's obvious; ask only if two are equally good.
3. **Read.** `bank show <id>`. Note its `inputs:` list and `uses:` dependencies (`bank deps <id>` if any).
4. **Use it.**
   - prompt → collect any missing inputs in ONE question, then `bank render <id> k=v k=@file …` and follow the rendered text as your instructions for this task (or show it if the user only wanted the text).
   - skill → follow its body as instructions for the current task. If the user wants it permanently available, `bank export-skill <id>` (becomes /<id> next session).
   - agent → treat the body as your system brief for the task.
   - tool / connector / instruction → summarise what it says and apply it.
5. **Create / improve** (when asked, or when nothing fits and the user agrees):
   - new: `bank create-skill "<one-sentence what + when>" --project <jobeng|buildings|interior|shared>`
   - improve: `bank create-skill --improve <id> "<feedback>"`
   - plain prompt: `bank new prompt <id>` then edit the file it prints and `bank validate`.
6. **Menu** (bare /skills-bank): `bank stats | head -12`, then offer: search · show · use · create · export · dashboard (`bank dashboard`).

## Output format
- One line saying which entry you used: `Using <id> (<type>) from the bank.`
- Then the actual work product of the task — not a description of the bank.
- After creating/exporting: the exact command run and the file path it printed.

## Rules
- Always go through the `bank` CLI; never edit bank files directly except the one `bank new` just created.
- Never invent an entry id — only use ids that `bank search` / `bank list` returned.
- Ask at most one clarifying question per step; batch missing inputs together.
- Don't export skills unless the user asks — keep ~/.claude/skills small.
- If `bank` isn't found: tell the user to run `sh ~/.skills-bank/install.sh` (or `pip install git+https://github.com/salahibrahimplq/skills-bank`) and stop.
- Respect the entry's `model:` hint only when the user is calling `bank run`; inside Claude Code, just do the work.

## Example
User: `/skills-bank write a rejection email for Ahmed, site engineer at Kier, after interview`
→ `bank search "rejection email"` → `jobeng-rejection-email (prompt, jobeng)`
→ `bank show jobeng-rejection-email` → inputs: candidate_first_name, role_title, company_name, stage, reason_category, keep_on_file
→ asks once: "Reason, and keep on file?" → user: "stronger candidates, yes"
→ `bank render jobeng-rejection-email candidate_first_name=Ahmed role_title="Site Engineer" company_name=Kier stage=interview reason_category=stronger-candidates keep_on_file=yes`
→ "Using jobeng-rejection-email (prompt) from the bank." + the finished email.
