export async function startOrchestrate(topic: string, criteria: string[], context?: string) {
  const criteriaChunk = criteria.join(", ");
  const res = await fetch("/agents/orchestrate", {
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
  if (!data.success) {
    throw new Error("PPT generation failed: " + JSON.stringify(data.qc_results));
  }
  return data;
}

export function fileUrl() {
  return `/agents/files/output.pptx`;
}
