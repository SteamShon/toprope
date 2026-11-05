# Product note: version control and review for domain models

- Link: none (a product idea outside the claim chain). Status: note, not a decision.
- Date: 2026-11-05. Raised by the researcher; written up by the assistant.

## The idea
A small product: "GitHub for domain models and ontologies". A domain spec is kept as
immutable commits. Its changes are reviewed as a **semantic diff**: elements added, removed
and changed, classified as breaking or not. Only approved commits are deployed, and before a
deploy the person sees every change since the last deploy and confirms it. The spec maps to
open formats (OWL, LinkML) or to a Foundry-style ontology (object types, links, actions), so
it is useful without the rest of Toprope.

## Why there may be room
- **Open-source diff tools for ontologies are thin or old.**
  - [owlcompare](https://pypi.org/project/owlcompare/) is the closest. It is pre-alpha: a
    semantic OWL diff with a GitHub Action that comments on PRs and fails on breaking
    changes. It notes that axiom-level diffs (ROBOT, owl-diff, Protégé) are hard for people
    to read.
  - [owl2vcs](https://github.com/utapyngo/owl2vcs) and
    [OWLDiff](https://kbss.felk.cvut.cz/tools/owldiff) are older.
  - CODEX and SemVersion are research prototypes.
  - No LinkML-specific diff tool turned up.
- **Foundry already has the workflow, but closed.** Ontology changes are proposals on
  branches, reviewed and merged into a protected main
  ([branching](https://palantir.com/docs/foundry/ontologies/branching-ontology/),
  [proposals](https://palantir.com/docs/foundry/ontologies/review-ontology-proposals/)).
  The new Global Branching is in limited beta
  ([overview](https://palantir.com/docs/foundry/foundry-branching/overview)). Nothing gives
  this experience outside Foundry.
- **The API world shows the pattern works.** oasdiff (OpenAPI) and buf (protobuf) classify
  changes as breaking or not and report them in PRs. No such tool exists for domain specs.

## What Toprope already has
Toprope already has the core: the commit store, review hash, semantic diff (`review_diff`),
approval tags and the deploy floor, plus branches (ADR-0033). Still missing:
- exporters and importers for OWL, LinkML or a Foundry-style ontology
- breaking-change classification
- a review UI, or PR comments, that shows the diff well. This is the hard part (the
  researcher's probe P06).

## Open questions
- Who is the user: ontology engineers, data platform teams, or teams moving off Foundry?
- Which format comes first: LinkML (Python, open schemas), OWL, or a Foundry mapping?
- How should a semantic diff look to a reviewer who is not a modeler?
- Should it ship as a CLI and GitHub Action first, the way owlcompare does?
