<script lang="ts">
  import { startOrchestrate, fileUrl, makeRunEventSource } from "$lib/store/agents";
  import { continueRun } from "$lib/store/continueRun";
  // State for user intervention
  let userInputNeeded = false;
  let failedCriteria: {criterion: string, reason: string}[] = [];
  let runIdForContinue: string | null = null;
  let skipChoices: Record<string, boolean> = {};
  let continueError = "";

  let topic = "";
  let criteriaText = "At least 6 slides, Each slide has a title, Each slide has at least 2 bullets, No slide has more than 5 bullets";
  let context = "";

  let qcResults: any[] = [];
  let pptDownloadHref: string | null = null;
  let running = false;
  let errorMsg = "";
  let logs: {type:string, message?:string, criterion?:string, result?:string, reason?:string}[] = [];
  let es: EventSource | null = null;

  async function onSubmit() {
    errorMsg = "";
    qcResults = [];
    pptDownloadHref = null;

    const criteria = criteriaText.split(",").map(s => s.trim()).filter(Boolean);
    if (!topic || criteria.length === 0) {
      errorMsg = "Please enter topic and at least one criterion.";
      return;
    }

    logs = [];
    running = true;
    try {
      const startResp = await startOrchestrate(topic, criteria, context || undefined);
      const runId = startResp.run_id;
      // open EventSource
      es = makeRunEventSource(runId);
      es.onmessage = (evt) => {
        try {
          const obj = JSON.parse(evt.data);
          if (obj.type === 'log') {
            logs = [...logs, {type: 'log', message: obj.message}];
          } else if (obj.type === 'qc') {
            logs = [...logs, {type: 'qc', criterion: obj.criterion, result: obj.result, reason: obj.reason}];
          } else if (obj.type === 'user_input_needed') {
            // Pause run, show user input UI
            userInputNeeded = true;
            failedCriteria = obj.failed_criteria || [];
            runIdForContinue = obj.run_id;
            skipChoices = {};
            failedCriteria.forEach(fc => { skipChoices[fc.criterion] = false; });
            running = false;
            logs = [...logs, {type: 'log', message: obj.message || 'User input needed.'}];
            es?.close();
            es = null;
          } else if (obj.type === 'done') {
            if (obj.success) {
              qcResults = obj.qc_results || [];
              pptDownloadHref = fileUrl();
            } else {
              errorMsg = obj.error || 'Generation failed';
            }
            logs = [...logs, {type: 'log', message: 'Run finished.'}];
            running = false;
            es?.close();
            es = null;
          }
        } catch (e) {
          logs = [...logs, {type: 'log', message: evt.data}];
        }
      };
      es.onerror = (e) => {
        logs = [...logs, {type: 'log', message: 'Stream error or closed.'}];
        running = false;
        es?.close();
        es = null;
      };
    } catch (err: any) {
      errorMsg = err?.message || String(err);
      running = false;
    }
  }
</script>

<!-- User input dialog for skip/retry failed criteria -->
{#if userInputNeeded}
  <div class="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
    <div class="bg-white rounded-lg shadow-lg p-6 w-full max-w-lg">
      <h2 class="text-lg font-bold mb-2">Some criteria could not be satisfied</h2>
      <p class="mb-4">Choose which criteria to <span class="font-semibold">skip</span> (unselected will be retried):</p>
      <form on:submit|preventDefault={async () => {
        continueError = "";
        try {
          if (!runIdForContinue) return;
          const skipList = Object.entries(skipChoices).filter(([_, v]) => v).map(([k]) => k);
          await continueRun(runIdForContinue, skipList);
          userInputNeeded = false;
          running = true;
          // Re-open EventSource for this run
          es = makeRunEventSource(runIdForContinue);
          es.onmessage = (evt) => {
            try {
              const obj = JSON.parse(evt.data);
              if (obj.type === 'log') {
                logs = [...logs, {type: 'log', message: obj.message}];
              } else if (obj.type === 'qc') {
                logs = [...logs, {type: 'qc', criterion: obj.criterion, result: obj.result, reason: obj.reason}];
              } else if (obj.type === 'user_input_needed') {
                userInputNeeded = true;
                failedCriteria = obj.failed_criteria || [];
                runIdForContinue = obj.run_id;
                skipChoices = {};
                failedCriteria.forEach(fc => { skipChoices[fc.criterion] = false; });
                running = false;
                logs = [...logs, {type: 'log', message: obj.message || 'User input needed.'}];
                es?.close();
                es = null;
              } else if (obj.type === 'done') {
                if (obj.success) {
                  qcResults = obj.qc_results || [];
                  pptDownloadHref = fileUrl();
                } else {
                  errorMsg = obj.error || 'Generation failed';
                }
                logs = [...logs, {type: 'log', message: 'Run finished.'}];
                running = false;
                es?.close();
                es = null;
              }
            } catch (e) {
              logs = [...logs, {type: 'log', message: evt.data}];
            }
          };
          es.onerror = (e) => {
            logs = [...logs, {type: 'log', message: 'Stream error or closed.'}];
            running = false;
            es?.close();
            es = null;
          };
        } catch (err) {
          continueError = err?.message || String(err);
        }
      }}>
        <ul class="mb-4">
          {#each failedCriteria as fc}
            <li class="flex items-center mb-2">
              <input type="checkbox" id={fc.criterion} bind:checked={skipChoices[fc.criterion]} class="mr-2" />
              <label for={fc.criterion} class="flex-1">
                <span class="font-semibold">{fc.criterion}</span>
                <span class="ml-2 text-gray-500">({fc.reason})</span>
              </label>
            </li>
          {/each}
        </ul>
        {#if continueError}
          <div class="text-red-500 mb-2">{continueError}</div>
        {/if}
        <div class="flex gap-2 justify-end">
          <button type="submit" class="px-4 py-2 rounded bg-black text-white">Continue</button>
          <button type="button" class="px-4 py-2 rounded bg-gray-300 text-black" on:click={() => { userInputNeeded = false; }}>Cancel</button>
        </div>
      </form>
    </div>
  </div>
{/if}

<div class="max-w-4xl mx-auto p-6 space-y-6">
  <h1 class="text-2xl font-bold text-white">PPT Generator (Agno)</h1>

  <div class="grid gap-3 md:grid-cols-2">
    <div>
      <label class="block text-sm text-white/90">Topic</label>
      <input class="w-full rounded p-2 bg-white/10 text-white border border-white/20" bind:value={topic} placeholder="Topic (e.g., GenAI market landscape)" />
      <label class="block mt-3 text-sm text-white/90">Criteria</label>
      <textarea class="w-full rounded p-2 h-28 bg-white/10 text-white border border-white/20" bind:value={criteriaText} placeholder="Criteria (comma-separated)"></textarea>
      <label class="block mt-3 text-sm text-white/90">Optional context</label>
      <input class="w-full rounded p-2 bg-white/10 text-white border border-white/20" bind:value={context} placeholder="Optional context (persona/style/etc.)" />
      <div class="mt-4">
        <button class="px-4 py-2 rounded bg-black text-white disabled:opacity-50" on:click={onSubmit} disabled={running}>
          {running ? "Running..." : "Generate PPT"}
        </button>
        {#if errorMsg}<p class="text-red-400 mt-2">{errorMsg}</p>{/if}
      </div>
      {#if pptDownloadHref}
        <div class="mt-4">
          <a class="inline-block px-4 py-2 rounded bg-green-600 text-white" href={pptDownloadHref}>
            Download PPT
          </a>
        </div>
      {/if}
    </div>

    <div>
      <label class="block text-sm text-white/90">Agno Log / Live Output</label>
      <div class="mt-2 h-80 overflow-y-auto bg-white/10 rounded p-3 text-white text-sm" id="logpane">
        {#each logs as l}
          {#if l.type === 'log'}
            <div class="mb-1">{l.message}</div>
          {:else if l.type === 'qc'}
            <div class="mb-1"><strong>{l.criterion}</strong>: {l.result} — {l.reason}</div>
          {/if}
        {/each}
      </div>
    </div>
  </div>

  {#if qcResults.length}
    <div>
      <h2 class="font-semibold text-white/90">Quality Check</h2>
      <table class="w-full border text-sm text-white">
        <thead>
          <tr class="bg-white/10">
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
</div>
