# Skill: Documentation that ships with code

## Purpose
Produce user-facing and maintainer-facing docs that are generated from observable repository state, not from intent.

## When to apply
A delivery node requires README, API docs, or run artifacts that explain how to use the built system.

## Method
1. Inspect the implemented code, CLI help, and tests to derive usage — do not copy the spec as documentation.
2. Structure: purpose → install → quick start (copy-pasteable) → configuration → verification → limits.
3. Include exact commands and their observed output paths. Every code block should have been executed.
4. Validate that examples run from a clean checkout when possible.
5. Keep docs inside their declared `write_scope` (`docs/**` or `README.md` at root only when explicitly scoped).

## Evidence
- Command + output for every documented workflow (install, template, open, result)
- Path to the rendered doc and its line count
