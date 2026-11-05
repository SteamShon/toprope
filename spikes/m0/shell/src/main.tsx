// Spike shell: render compiled A2UI messages (no LLM) with the basic catalog + one host component.
import React, { useEffect } from "react";
import { createRoot } from "react-dom/client";
import { z } from "zod";
import {
  A2UIProvider, A2UIRenderer, createCatalog, useA2UIActions, DynamicStringSchema,
} from "@copilotkit/a2ui-renderer";

declare global { interface Window { __actions: unknown[]; __ready?: boolean } }
window.__actions = [];

// Host-injected component (ADR-0008 overlay): registered in the renderer catalog.
const hostDefs = {
  AcmeStatusBadge: {
    description: "Acme's status badge (host component)",
    props: z.object({ status: DynamicStringSchema }),
  },
};
const catalog = createCatalog(hostDefs, {
  AcmeStatusBadge: ({ props }) => (
    <span data-testid="acme-badge" style={{ border: "1px solid #888", padding: "2px 8px", borderRadius: 8 }}>
      ACME · {String(props.status)}
    </span>
  ),
}, { catalogId: "toprope://catalog/spike-v1", includeBasicCatalog: true });

function Loader({ file }: { file: string }) {
  const { processMessages } = useA2UIActions();
  useEffect(() => {
    fetch(file).then((r) => r.json()).then((msgs) => { processMessages(msgs); window.__ready = true; });
  }, [file]);
  return null;
}

const file = new URLSearchParams(location.search).get("m") ?? "messages.json";
createRoot(document.getElementById("root")!).render(
  <A2UIProvider catalog={catalog} onAction={(m) => { window.__actions.push(m); }}>
    <Loader file={file} />
    <A2UIRenderer surfaceId="Experiment.detail:E1" fallback={<div>waiting…</div>} />
  </A2UIProvider>,
);
