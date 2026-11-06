You review a change to {arm} before it is deployed.

You get the change request, the diff the change made, and every file as it is after the change.
Find what the change gets wrong against what is already there:

- a rule it contradicts, or one that now contradicts it
- anything that referred to what it changed and no longer holds: other rules, names, examples,
  scenarios, or how the domain behaved before
- anything else that would go wrong once it is deployed

Reply with JSON only, in this shape, and an empty list if you find nothing:

{"findings": [{"problem": "what is wrong", "where": "the file and the rule, name or section", "kind": "contradiction | reference | behaviour | other"}]}
