# FormalPrompt seed artifact library

This directory is a selection library for the initialization composer, not a package that every
project receives. Muse should select the smallest applicable set, adapt it to the user-approved
specification, and copy the resulting content into the canvas as typed initialization artifacts.
Compiled workflow nodes reference those materialized artifacts, never this external directory.

`catalog.json` describes applicability and non-applicability without prescribing a fixed graph.
The seed artifacts encode current operating invariants; they are starting material for the planned
history-informed Muse tuning, not a claim that the best durable policies have already been found.

Changes to this library should be evaluated across several initialization cases. A local project
intervention is evidence for later analysis, not automatic authority to mutate a library artifact.
