# Bounded implementation

Read the verified execution contract, the active node, and only its referenced resources. Inspect
the actual repository state before changing it. Implement the user-approved outcome within the
declared write scope and preserve existing behavior outside that scope. Verify the result against
the node's observable acceptance criteria.

If physical state invalidates an implementation detail, choose the narrowest fidelity-preserving
adaptation allowed by policy. A consequential change to intent, authority, model assignment, or
completion criteria returns to the declared user-decision path.
