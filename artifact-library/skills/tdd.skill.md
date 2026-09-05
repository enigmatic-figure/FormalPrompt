# Skill: Test-driven development

## Purpose
Drive implementation through observable acceptance criteria before or alongside code changes. Keep the test as the specification of done.

## When to apply
An `agent` or `operation` node lists testable `acceptance_criteria` and has a non-empty `write_scope` that includes tests.

## Method
1. For each criterion, draft the minimal test that would prove it — happy path first, then edge/failure cases that the spec implies.
2. Place tests inside `write_scope` (`tests/**` or co-located per repo conventions).
3. Run the new tests to see them fail for the right reason before implementing. Capture output.
4. Implement the smallest code that makes the new tests pass while keeping existing tests green. Do not add speculative generality.
5. Verify with the node''s prescribed checks (`pytest`, lint, build) and report evidence paths.

## Evidence expected
- Test file paths and names per criterion
- Failing-then-passing transition captured (stdout tail)
- Final test run result (pass count, command)

## Pitfalls
- Do not write tests that mirror implementation details instead of acceptance criteria.
- Do not claim coverage by file existence; a passing run is the evidence.
