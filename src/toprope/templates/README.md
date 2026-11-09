# Templates

Link: none (content, ADR-0049 A3). These are declarations of everyday workflows that
`toprope-init` copies to start a domain, and that `toprope-try` plays. Each directory has:

- `domain.yaml`: the declaration;
- `tokens.yaml`: the people and the agent of its story (static identities, for trying it);
- `story.yaml`: the steps `toprope-try` plays, each with who asks, what, and how it should end.

**They are content, not the kernel.** No kernel code reads them or depends on them: the kernel
compiles and enforces any declaration the same way. Changing a template is a change of example
content, not of Toprope's behaviour, and needs no ADR. A template must pass its harness and its
own story (`tests/test_init_try.py`).

**They are the source for two examples.** `examples/refunds/` and `examples/paid-media/` show
the `refunds` and `budget` templates with a README and a changed version for the change check.
Edit the template, then copy its `domain.yaml` and `tokens.yaml` there (`paid-media` keeps its
own `domain:` name); `tests/test_init_try.py` fails while they differ.
