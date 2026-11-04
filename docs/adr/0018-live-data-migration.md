# ADR-0018: Live-data migration and in-flight checks move into the change check

- Link: ① iterate safely, ③ works as built · Status: accepted · 2026-11-04 · decided by: SteamShon
- Origin: design review 2026-11-04 (finding 4)

## Context
P0 means a domain is changed while it is in use. Removing or renaming a state, or adding a
required field, strands live objects. This was deferred, but the M2 dogfood use runs
straight into it.

## Decision
1. **In-flight check** in the change check (ADR-0009). Project the current live state and
   list the objects the change would strand. Examples: objects in a removed state, objects
   that now violate an invariant, objects missing a newly required field.
2. **Migration plan** is required for a change with stranded objects. It is declared next to
   the change:
   - map old states to new ones
   - set defaults for new fields
   - or keep the objects on the old version until they finish.

   The plan is itself tested: replaying it on the projected live state must satisfy every
   invariant of the new version.
3. **Events are never rewritten.** Migration is a new event (`Migrated`) per object, plus
   upcasters for old event shapes (ADR-0012).
4. **Deploy gate** adds two conditions: no stranded objects without a plan, and a passing
   migration test.

## Consequences
- Moves from "later" to M0b (built) and M2 (used for real).
- Impact reports (ADR-0013) list stranded live objects next to affected tests.
