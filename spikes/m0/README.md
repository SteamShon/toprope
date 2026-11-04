# M0 spike (throwaway)

Link: none (enabler). This is spike code. It answers the integration questions in ADR-0017
before the kernel is built, and is **not** the kernel. Findings:
[`docs/experiments/M0-spike-report.md`](../../docs/experiments/M0-spike-report.md).

## A. `toprope-server` shape: MCP generated from a declaration
```bash
cd server
uv run python spike_check.py                       # in-process
uv run python -m toprope_spike.server toy.domain.yaml streamable-http &   # http://127.0.0.1:8765/mcp
uv run python spike_check.py http://127.0.0.1:8765/mcp
uv run python spike_check_stdio.py                 # stdio, the transport Claude Code launches
```
Connect Claude Code (stdio):
```bash
claude mcp add toprope-spike -- uv run --directory "$PWD" python -m toprope_spike.server toy.domain.yaml stdio
```

## B. `toprope-shell` shape: compiled A2UI + host component
```bash
cd server && uv run python -m toprope_spike.a2ui --role approver --overlay > ../shell/public/appr.json
uv run python -m toprope_spike.a2ui --role eng --overlay > ../shell/public/eng.json
cd ../shell && npm ci && npx esbuild src/main.tsx --bundle --outfile=public/app.js --jsx=automatic \
  --define:process.env.NODE_ENV='"production"'
(cd public && python3 -m http.server 8770 &) && node check.cjs http://127.0.0.1:8770
```
