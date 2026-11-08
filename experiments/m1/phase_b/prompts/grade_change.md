You grade one change in an experiment. You are given the change request, the problem the
researcher seeded in it (the answer key: `none`, or a conflict or breakage and what it is against),
and the elements the request is bound to. Then, under the labels A, B and C, three versions of the
same change: each label's edit, and the flags its pre-deploy checks raised, run by run. Each flag
has an id (`label.run.index`). Grade every label on the same scale.

Label every flag, by its id:
- `seeded`: it identifies the seeded problem (the same conflict or breakage, in any words)
- `other-real`: it is a real problem with this change, but not the seeded one
- `false-alarm`: it is not a real problem

Then judge each label's edit: did it implement the request (`implements`), only part of it
(`partial`), or not at all (`does-not`)? Judge only whether it does what was asked, not whether
that is wise.

Reply with JSON only:
{"flags": [{"id": "A.1.0", "label": "seeded | other-real | false-alarm", "why": "one sentence"}],
 "edits": [{"label": "A", "fidelity": "implements | partial | does-not", "why": "one sentence"}]}
