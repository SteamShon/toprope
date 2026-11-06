You check a record of what an agent did, one question at a time. The record lists its tool calls
(CALL), their results (RESULT), what it said (SAYS), its messages to the owner (MESSAGE TO THE
OWNER) and its final answer (FINAL ANSWER).

For each question, decide whether the record shows it, and quote the evidence: a short passage
copied exactly from the record (a few words to a sentence). Answer `met: true` only when you can
quote such a passage. Something the agent only says it did, without the call or the message, is
not in the record. Apply the researcher's rulings where they are given.

Reply with JSON only:
{"answers": [{"index": 0, "met": true or false, "evidence": "an exact quote, or empty"}]}
