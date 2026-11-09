"""Grouped findings in the change report (M1-report, *What M2 takes from this* 4)."""

from toprope.check import ChangeReport, CheckResult


def test_a_log_replay_that_repeats_itself_is_one_group():
    replay = CheckResult("log_replay")
    for i in range(64):
        replay.add("warning", f"E-{i}@1",
                   f"propose_element at 2026-11-06T17:29:{i % 60:02d}.905181+00:00 would now set ['drafted_by'] different")
    replay.add("error", "E-9@2", "decide at 2026-11-06T18:00:00+00:00 would now be blocked")
    structural = CheckResult("structural")
    structural.add("warning", "actions.add_source.params", "unset-on-create: add_source")
    r = ChangeReport("d", {}, {"log_replay": replay, "structural": structural})
    groups = r.groups()
    assert [(g["check"], g["severity"], g["count"]) for g in groups] == [
        ("log_replay", "error", 1), ("log_replay", "warning", 64), ("structural", "warning", 1)]
    assert groups[1]["problem"] == "propose_element at <time> would now set ['drafted_by'] different"
    assert groups[1]["where"] == ["E-0@1", "E-1@1", "E-2@1"] and r.to_json()["groups"] == groups
