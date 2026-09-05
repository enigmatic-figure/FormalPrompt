# Skill: API and contract design

## Purpose
Produce a strict, versioned contract that two subsystems (or human and agent) can independently verify.

## When to apply
A feature requires a boundary between components, services, or agents with typed data exchange.

## Method
1. Extract the contract from spec fields and predecessor artifacts. Preserve explicit names; flag inferred fields with rationale.
2. Model the contract with strict schemas (`extra="forbid"`), explicit required/optional markers, and enumerated values where the spec names them.
3. Add example valid and invalid payloads that show what the validator rejects.
4. Define compatibility and versioning rules.
5. Declare the evidence that proves adherence (schema validation run, example payload check, interop test).

## Outputs
- Contract artifact (JSON Schema, Pydantic model spec, or markdown table with formal schema block)
- Example payloads and the command that validates them

## Validation
`validate_document` or a typed model loader should reject unknown fields. A missing field should fail fast, not silently default.
