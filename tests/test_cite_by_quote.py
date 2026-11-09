"""A citation may quote the passage instead of naming its chunk (ADR-0049, B4). It records the
chunk the words resolve to, so provenance stays a pointer that resolves."""
import pytest
from test_authoring import ws  # noqa: F401  (the workspace fixture)
from test_commit_evidence import cite, kernel  # noqa: F401  (the kernel fixture)

from toprope.workspace import AuthoringError

REF = "docs:docs/process.md#L4-L6"


def test_words_from_one_passage_resolve_to_its_chunk_and_keep_the_quote(ws):  # noqa: F811
    ws.propose("objects.Experiment", {"description": "A test."}, 'docs: "every  experiment needs an APPROVER"')
    assert ws.draft()["objects"]["Experiment"]["source"] == {
        "kind": "record", "ref": REF, "quote": "every  experiment needs an APPROVER"}


def test_an_exact_ref_is_kept_as_it_is(ws):  # noqa: F811
    ws.propose("objects.Experiment", {"description": "A test."}, REF, quote="the owner's words")
    assert ws.draft()["objects"]["Experiment"]["source"] == {"kind": "record", "ref": REF,
                                                             "quote": "the owner's words"}


def test_words_in_several_passages_are_refused_with_the_candidates(ws):  # noqa: F811
    with pytest.raises(AuthoringError) as e:
        ws.propose("roles", ["approver"], "Every experiment needs an approver")    # in `docs` and in `all`
    msg = str(e.value)
    assert "2 passages contain" in msg and REF in msg and "Fix: quote more of the passage" in msg


def test_words_in_no_passage_are_refused_with_the_fix(ws):  # noqa: F811
    with pytest.raises(AuthoringError, match="no passage contains those words. Fix: run `search`"):
        ws.propose("roles", ["approver"], "docs: nobody writes this sentence")


def test_a_local_only_source_is_not_searched_unless_named(ws):  # noqa: F811
    with pytest.raises(AuthoringError, match="no passage contains"):
        ws.propose("roles", ["approver"], "PMs never approve")
    ref, quoted = ws.resolve_ref("sessions: PMs never approve")
    assert ref.startswith("sessions:") and quoted == "PMs never approve"


def test_a_single_token_is_still_read_as_a_ref(ws):  # noqa: F811
    with pytest.raises(AuthoringError, match="no chunk 'docs:docs/process.md#L99-L100'. Fix:"):
        ws.propose("objects.Ghost", {}, "docs:docs/process.md#L99-L100")
    with pytest.raises(AuthoringError, match="unknown source in ref 'nowhere:x#L1'. Fix:"):
        ws.propose("objects.Ghost", {}, "nowhere:x#L1")


def test_evidence_cited_by_quote_records_the_chunk(kernel):  # noqa: F811
    k, c = kernel
    assert cite(k, c, "source", "Every experiment needs an approver.")["strength"] == "pointed"
    assert [r["ref"] for r in k.commits.evidence("example", c)] == [k.workspace.chunks("docs")[0].ref]


def test_evidence_by_quote_of_an_interview_line_must_be_cited_as_interview(kernel):  # noqa: F811
    k, c = kernel
    out = cite(k, c, "source", "interview: A lead.")
    assert not out["ok"] and "not a source" in out["error"] and "--kind interview" in out["error"]
