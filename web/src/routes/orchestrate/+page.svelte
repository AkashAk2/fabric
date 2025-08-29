<script lang="ts">
  import { startOrchestrate, fileUrl } from "$lib/store/agents";

  let topic = "";
  let criteriaText = "At least 6 slides, Each slide has a title, Each slide has at least 2 bullets, No slide has more than 5 bullets";
  let context = "";

  let qcResults: any[] = [];
  let pptDownloadHref: string | null = null;
  let running = false;
  let errorMsg = "";

  async function onSubmit() {
    errorMsg = "";
    qcResults = [];
    pptDownloadHref = null;

    const criteria = criteriaText.split(",").map(s => s.trim()).filter(Boolean);
    if (!topic || criteria.length === 0) {
      errorMsg = "Please enter topic and at least one criterion.";
      return;
    }

    running = true;
    try {
      const data = await startOrchestrate(topic, criteria, context || undefined);
      qcResults = data.qc_results || [];
      pptDownloadHref = fileUrl();
      running = false;
    } catch (err: any) {
      errorMsg = err?.message || String(err);
      running = false;
    }
  }
</script>

<div class="max-w-3xl mx-auto p-6 space-y-6">
  <h1 class="text-2xl font-bold">PPT Generator (Agno)</h1>

  <div class="grid gap-3">
    <input class="border rounded p-2" bind:value={topic} placeholder="Topic (e.g., GenAI market landscape)" />
    <textarea class="border rounded p-2 h-24" bind:value={criteriaText} placeholder="Criteria (comma-separated)"></textarea>
    <input class="border rounded p-2" bind:value={context} placeholder="Optional context (persona/style/etc.)" />
    <button class="px-4 py-2 rounded bg-black text-white disabled:opacity-50" on:click={onSubmit} disabled={running}>
      {running ? "Running..." : "Generate PPT"}
    </button>
    {#if errorMsg}<p class="text-red-600">{errorMsg}</p>{/if}
  </div>

  {#if qcResults.length}
    <div>
      <h2 class="font-semibold">Quality Check</h2>
      <table class="w-full border text-sm">
        <thead>
          <tr class="bg-gray-100">
            <th class="text-left p-2 border">Criterion</th>
            <th class="text-left p-2 border">Result</th>
            <th class="text-left p-2 border">Reason</th>
          </tr>
        </thead>
        <tbody>
          {#each qcResults as r}
            <tr>
              <td class="p-2 border">{r.criterion}</td>
              <td class="p-2 border">{r.result}</td>
              <td class="p-2 border">{r.reason}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}

  {#if pptDownloadHref}
    <a class="inline-block px-4 py-2 rounded bg-green-600 text-white" href={pptDownloadHref}>
      Download PPT
    </a>
  {/if}
</div>
