# API contract — typed, verifiable

Define a machine-checkable interface between two subsystems named in the spec.

Instructions:
1. Extract the exact endpoints/symbols, request/response shapes, and error semantics from the spec fields. Preserve explicit names; mark inferred shapes with rationale.
2. Declare the contract as typed schemas (Pydantic models, JSON Schema, or OpenAPI subset) with strict `extra="forbid"` where appropriate. Unrecognized fields should be rejected, not ignored.
3. Specify readiness: what evidence proves the contract is satisfied (schema validation, example payloads, interop test).
4. State versioning and backward-compatibility boundary if the spec names one.

Deliverable: a single contract artifact (e.g., `docs/contracts/<name>.md` or `schemas/<name>.json`) inside `write_scope`. Implementation nodes will bind this artifact as a resource and verify against it.
