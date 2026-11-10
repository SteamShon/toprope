You grade one change in an experiment. You are given the change request, the problem the
researcher seeded in it (the answer key: `none`, or a conflict or breakage and what it is
against), and the elements the request is bound to. Then, under the labels A, B and C, three
versions of the same change: each label's edit, and the distinct flags its pre-deploy checks
raised. Each flag has an id. Judge every flag on the same scale.

For each flag, answer four questions with true or false. Answer each one on its own. Do not decide
an overall label: the answers are combined by a fixed rule.

- `names`: Does the flag name the same rule, action, object or behaviour that the key's `against`
  names, or one that plainly stands for it? (False when the key's problem is `none`.)
- `conflict`: Does the flag say that the change conflicts with it, breaks it, or makes it untrue?
- `outcome`: Would the outcome the flag describes break that rule or behaviour, even if the flag
  calls it a gap in the implementation, a missing check, or a risk rather than a conflict?
  (Rule B. Example of true: the key says "only a person confirms an element"; the flag says "the new
  action lets an agent mark an element confirmed without a check". Example of false: the same key;
  the flag says "the new action's description is unclear".)
- `real`: Is it a real problem with this change, whatever the key says? (False for a statement
  that is only a summary, a restatement of the change, or wrong about the declarations.)

Then judge each label's edit: did it implement the request (`implements`), only part of it
(`partial`), or not at all (`does-not`)? Judge only whether it does what was asked, not whether
that is wise.

Reply with JSON only:
{"flags": [{"id": "A.u0", "names": true, "conflict": false, "outcome": true, "real": true, "why": "one sentence"}],
 "edits": [{"label": "A", "fidelity": "implements | partial | does-not", "why": "one sentence"}]}
