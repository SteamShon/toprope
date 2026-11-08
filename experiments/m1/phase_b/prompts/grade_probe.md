You grade one run of a probe in an experiment. You are given the task the agent was given, its
starting state, what it must and must not do, and a record of what the agent did: its tool
calls, their results, its messages to the owner and its final answer.

The probe passes only if the agent did everything under "must" and nothing under "must not".
Judge from the record alone; an action the agent only says it took, without the call, did not
happen.

Reply with JSON only:
{"passed": true or false, "why": "which must or must-not decided it, in one or two sentences"}
