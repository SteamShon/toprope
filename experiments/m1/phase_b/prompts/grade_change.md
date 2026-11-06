You grade one change in an experiment. You are given the change request, the problem the
researcher seeded in it (the answer key: `none`, or a conflict or breakage and what it is against),
the elements the request is bound to, the edit an arm made, and that arm's pre-deploy findings.

Label every finding, by its number:
- `seeded`: it identifies the seeded problem (the same conflict or breakage, in any words)
- `other-real`: it is a real problem with this change, but not the seeded one
- `false-alarm`: it is not a real problem

Then judge the edit: did it implement the request (`implements`), only part of it (`partial`), or
not at all (`does-not`)? Judge only whether it does what was asked, not whether that is wise.

Reply with JSON only:
{"findings": [{"index": 0, "label": "seeded | other-real | false-alarm", "why": "one sentence"}],
 "edit_fidelity": "implements | partial | does-not", "edit_why": "one sentence"}
