You are writing a skill file for a coding agent.

The workspace holds the declarations of two domains and the composition that joins them. Write
`SKILL.md`: the instructions an agent follows to work in these two domains, in plain prose, with
nothing left out. A reader who has only `SKILL.md` must be able to follow every rule the
declarations hold:

- the roles, and who may take each action
- the objects, their properties and the states each one moves through
- every action: who takes it, what it needs first, what it changes, and which actions only a
  person may take
- the transitions, and what is not allowed in each state
- the invariants
- the handoff between the two domains: what is sent, and what the receiver needs
- the glossary

Then write the declarations' scenarios as worked examples in `EXAMPLES.md`, one per scenario.

Do not add a rule the declarations do not hold, and do not drop one. Do not copy the YAML; write
prose and tables. Use the tools to read the files and to write the two new ones. When both are
written, reply with one line saying so.
