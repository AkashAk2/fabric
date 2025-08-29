export async function startOrchestrate(topic: string, criteria: string[], context?: string) {
  const criteriaChunk = criteria.join(", ");
  // Use streaming start endpoint so client can receive logs via SSE
  const res = await fetch("/agents/generate-stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      topic,
      agent_context: context || null,
      criteria_chunk: criteriaChunk
    })
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail?.message || `orchestrate failed: ${res.status}`);
  }
  const data = await res.json();
  return data;
}

export function fileUrl() {
  return `/agents/files/output.pptx`;
}

export function makeRunEventSource(runId: string) {
  // Fabric proxies /agents/runs/{id}/stream -> Agno
  const url = `/agents/runs/${runId}/stream`;
  return new EventSource(url);
}
