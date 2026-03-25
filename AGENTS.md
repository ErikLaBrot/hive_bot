# AGENTS.md

## Purpose

This file defines how work should be done in this repository.

It governs:
- workflow
- issue and PR hygiene
- engineering standards
- testing expectations
- documentation expectations
- repository structure and modularity rules

It does not define the current feature scope. Feature scope belongs in the active milestone document.

---

## Workflow model

Use issue-driven and PR-driven development.

Plan work through GitHub issues, then implement issue by issue.

An issue should represent a meaningful, complete unit of work, such as:
- a feature
- a bug
- a documentation task
- an improvement

Rules:
- a feature issue includes the feature, its tests, and its documentation
- a bug issue includes the fix, its regression tests, and any needed documentation updates
- an improvement issue includes the change, its tests, and any needed documentation updates
- documentation-only issues should exist only when documentation is independently deficient and needs isolated work
- test-only issues should exist only when test coverage or test quality is independently deficient and needs isolated work
- do not force an arbitrary number of issues
- do not split implementation, testing, and documentation into separate issues unless there is a clear reason
- do not combine unrelated work into one issue

Preferred flow:
1. read `AGENTS.md`
2. read the active milestone document
3. plan milestone work as GitHub issues
4. relate each issue to the active milestone
5. work one issue at a time
6. keep each PR scoped to one issue whenever practical
7. complete implementation, tests, coverage, and documentation as part of that issue

Each issue should have:
- a clear purpose
- clear scope boundaries
- completion criteria

Each PR should:
- address a single issue whenever practical
- stay focused on the scoped work
- include the tests and docs required to complete that issue
- avoid unrelated refactors
- reference the issue it addresses

---

## Git and GitHub rules

- Keep diffs small
- Prefer one branch per issue
- Prefer one PR per issue whenever practical
- Reference the issue being addressed in the PR
- Do not mix unrelated changes
- Do not rewrite large parts of the project without a clear issue requiring it
- Use issues to plan milestone work before implementation begins
- Do not split a feature into separate implementation, testing, and documentation issues unless there is a clear reason

If GitHub access is available, use it to:
- plan milestone work as issues
- keep issue scope clear
- implement work issue by issue
- prepare focused PRs

If Github access is available, do not:
- Merge PRs
- Close Issues
- Merge branches

Never expose, print, commit, or modify secrets or tokens.

---

## Engineering rules

- Keep diffs small
- Keep files modular
- Write documented code
- Write testable code
- Enforce strict linting and static analysis
- No task is complete without docs
- No task is complete without 100 percent test coverage for all code under the milestone

Do not introduce unrelated refactors.

---

## Structure rules

Use narrow file responsibilities.

Prefer small, focused modules over large multi-purpose files.

General guidance:
- startup code should stay separate from feature logic
- configuration loading should stay separate from runtime behavior
- command handlers should stay separate from service clients
- shared utilities should remain small and clearly scoped
- avoid coupling unrelated modules together

Create new files only when they improve clarity or separation of responsibility.

---

## Responsibility boundaries

Each file should have one narrow, obvious purpose.

Examples of good separation:
- application startup in one file
- configuration loading in one file
- logging setup in one file
- command handlers in their own modules
- service clients in their own modules

Do not mix unrelated responsibilities in one file.

---

## Quality requirements

All code must be:
- modular
- readable
- documented
- testable

Avoid:
- speculative abstractions
- giant utility files
- tight coupling between modules

---

## Tooling expectations

Set up and use a strict quality toolchain.

At minimum, include:
- formatter
- linter
- static analysis
- tests with coverage reporting

Use a Python toolchain appropriate for the project.

---

## Documentation expectations

Update documentation as part of the task.

At minimum:
- README with setup and run instructions
- milestone doc kept accurate
- code-level docstrings/comments where useful
- issue and PR descriptions kept aligned with the actual work

---

## Test expectations

Write tests for implemented code.

Target:
- 100 percent coverage for all code under the active milestone

Tests should verify real behavior, not just trivial execution.

---

## Definition of done

Done definitions depend on task.

Project planning is finished when:
- Finished when all items in the milestone are organized into GitHub Issues assigned to a Milestone

Issue/PR is finished when:
- The item scoped by the issue is completely implemented
- The item scoped by the PR has complete test code coverage in the context of the PR
- The item scoped by the PR has complete documentation
- The item scoped by the PR passes all formatting, linting, and static analysis
- The item scoped by the PR passes all test cases covering its context
- A human has reviewed and merged the code into the main branch

Milestone is finished when:
- All items in the milestone are completely implemented
- All items in the milestone have complete test code coverage
- All items in the milestone have complete documentation
- All issues in the milestone are closed with PRs and merged into the main branch
- The main branch passes all formatting, linting, static analysis, and test cases
- The main branch documentation and the README are completely updated

