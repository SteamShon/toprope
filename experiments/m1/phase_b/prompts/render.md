You are writing a skill file for a coding agent.

The workspace holds the declarations of two domains and the composition that joins them. Write
`SKILL.md`: the instructions an agent follows to work in these two domains, in plain prose and
tables, with nothing left out. A reader who has only `SKILL.md` must know every rule the
declarations hold, exactly as they hold it:

- the roles, and who may take each action
- each object's properties, with their types (string, integer, boolean, a list, a reference to
  another object, an enum and its values) and which are optional
- the links between objects
- every action: who takes it, its target or what it creates, each parameter with its type, and
  what it changes. Include every effect: each property it sets, and each kernel service it
  calls, by the service's name, with the arguments and the reply action. Say which actions only
  a person may take (`requires: human`) and which record a decision
- each action's named preconditions, with their ids, checks and reasons word for word. Keep them
  apart from the transition tables: a denial by a transition table is not a precondition
- the transitions: every cell of every table, with each deny reason word for word. Say nothing
  about cells a table does not list
- the invariants, with their ids, checks and reasons word for word
- the handoff between the two domains: what is sent, how it is wired, and what the receiver needs
- the glossary, word for word

Then write the declarations' scenarios as worked examples in `EXAMPLES.md`, one per scenario,
with every step and its expected outcome.

Write only what the declarations hold. Add no rule, explanation, advice or commentary of your own,
and do not infer rules that are not written there; leave out the `source` and `status` fields.
Do not copy the YAML; write prose and tables. Use the tools to read the files and to write the two
new ones. When both are written, reply with one line saying so.
