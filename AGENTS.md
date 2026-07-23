# AGENTS.md

## Purpose

This checkout is Amit's fork of Mealie and is the intended software foundation for a collaborative, agent-assisted household food-planning system.

- Local checkout: `/Users/vagabond/personal/mealie`
- Fork remote: `https://github.com/asaxena76/mealie.git`
- Upstream development base: `mealie-next`
- Local feature branch: `feature/carrie-integration`
- Deployment approach: not decided yet

## Product Context

The target weekly workflow is:

1. By Thursday, the household collaboratively chooses meals for the following week.
2. Recipes can come from Mealie's recipe database or begin as a plain-language description that an external agent turns into a reviewable recipe.
3. After the household explicitly approves the week, the system produces a consolidated grocery list for Friday shopping.
4. After shopping is reconciled, the system produces a Sunday batch-prep plan that prepares as much as is practical and organizes meal kits.
5. On cooking days, the household follows a short day-of execution plan and can adapt the remaining week when circumstances change.

The experience must preserve nuance. Meal planning is a conversation involving household preferences, schedule, leftovers, effort, variety, budget, food safety, and relevant dietary constraints. Automation should support collaborative decisions rather than silently make them.

## Intended System Boundaries

- Mealie is the system of record for structured recipes, ingredients, weekly meal plans, and grocery lists.
- Carrie, the external meal-planning agent, owns conversational reasoning, durable household meal-planning context, proposal generation, and orchestration through approved Mealie interfaces.
- Mealie should remain useful without Carrie. Prefer normal application APIs and domain objects over agent-only shortcuts.
- Sunday preparation, meal-kit assembly, assignments, storage guidance, thaw reminders, and approval state may require new capabilities. Do not assume their final design before discovery.
- Do not duplicate Carrie's private memory or personal health data in this repository.

## Human-in-the-Loop Requirements

Future agent integrations must follow these defaults:

1. Read the current state before proposing changes.
2. Present a draft meal plan and its important tradeoffs without writing it.
3. Require explicit human approval before committing a plan, grocery list, or preparation plan.
4. Show the downstream effects of later changes, including grocery and prep changes.
5. Re-read current application state before applying an approved change so human edits are not overwritten.
6. Keep all agent-created data editable through the normal Mealie interface.
7. Use a dedicated, least-privilege identity for agent access and never commit credentials or tokens.

## Current Phase

The repository is being established for future work. Do not make product-code or deployment changes until Amit selects the first scoped feature or deployment task. The next expected decision is how and where to deploy Mealie.

## Engineering Contract

- Read the relevant files under `docs/docs/contributors/developers-guide/` before non-trivial changes.
- Preserve compatibility with upstream Mealie where practical; branch work from `mealie-next` and keep changes reviewable.
- Follow the repository's existing Python, Vue, API, migration, localization, and code-generation conventions.
- Use the root `Taskfile.yml` as the command reference. The documented local setup is `task setup`; development servers are `task py` and `task ui`.
- Run focused tests while developing. Before handing off substantive backend work, run the relevant checks and `task py:check` when proportionate to the change.
- Update API and user documentation when behavior changes.
- Treat database migrations and recipe/shopping data transformations as high-risk: preserve existing data and test upgrade paths.
- Do not run `task dev:clean` without explicit approval; it deletes local development data.
- Contributions remain governed by the repository's AGPL license.

## Privacy and Test Data

- Never commit household names, health records, credentials, API keys, production exports, or Carrie's sidecar memory.
- Use fictional household members and recipes in fixtures, screenshots, logs, and tests.
- Access to Carrie's personal memory is controlled from the LMS repository at `/Users/vagabond/gwgt/amitlms/crew/hanuman`; this repository does not grant access to it.
