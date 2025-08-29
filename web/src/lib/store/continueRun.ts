export async function continueRun(runId: string, skipCriteria: string[]) {
  const res = await fetch("/agents/continue-run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_id: runId, skip_criteria: skipCriteria })
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.error || `continue-run failed: ${res.status}`);
  }
  return await res.json();
}
