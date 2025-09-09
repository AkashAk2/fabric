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
  let logs: {type:string, message?:string, criterion?:string, result?:string, reason?:string, stage?:string, role?:string, status?:string, event?:string}[] = [];
  let es: EventSource | null = null;

  function appendLog(entry: any) {
    logs = [...logs, entry];
    // Auto-scroll the log pane on next tick
    queueMicrotask(() => {
      const el = document.getElementById('logpane');
      if (el) el.scrollTop = el.scrollHeight;
    });
  }

  // Formatters and guards to prevent 'undefined' noise in the log view
  function toErrorMessage(e: unknown): string {
    if (typeof e === 'string') return e;
    const hasMessage = (x: unknown): x is { message: unknown } =>
      typeof x === 'object' && x !== null && Object.prototype.hasOwnProperty.call(x, 'message');
    if (hasMessage(e)) {
      const m = e.message;
      return typeof m === 'string' ? m : JSON.stringify(m);
    }
    try { return JSON.stringify(e); } catch { return String(e); }
  }

  function isNoisePayload(raw: string | null | undefined) {
    if (raw == null) return true;
    const t = String(raw).trim();
    return t === "" || t === "undefined" || t === "null" || t === "{}";
  }

  function formatStageMessage(obj: any) {
    const name = obj?.name || obj?.stage || "stage";
    const status = obj?.status || "";
    const attempt = obj?.attempt ? ` attempt_${obj.attempt}` : "";
    // Use detailed message if available, otherwise create a default one
    const msg = obj?.message && !isNoisePayload(obj.message) ? 
      obj.message : 
      `${name} ${status}${attempt}`.trim();
    return msg;
  }

  function formatAgentMessage(obj: any) {
    const role = obj?.role || "agent";
    const event = obj?.event;
    const stage = obj?.stage;
    const status = obj?.status;
    // Use detailed message if available
    if (obj?.message && !isNoisePayload(obj.message)) {
      return obj.message;
    }
    // Otherwise build a descriptive message
    let msg = "";
    if (event && !isNoisePayload(event)) msg = `${role} ${event}`;
    else if (stage || status) msg = `${role} ${stage || ""} ${status || ""}`.trim();
    else msg = role;
    return msg;
  }

  function handleSSEMessage(evt: MessageEvent) {
    const raw = evt.data;
    if (isNoisePayload(raw)) return; // ignore keep-alives or empty data
    try {
      const obj = JSON.parse(raw);
      if (obj.type === 'log') {
        if (!isNoisePayload(obj.message)) appendLog({type: 'log', message: obj.message});
      } else if (obj.type === 'qc') {
        appendLog({type: 'qc', criterion: obj.criterion, result: obj.result, reason: obj.reason});
      } else if (obj.type === 'stage') {
        const msg = formatStageMessage(obj);
        appendLog({type: 'log', stage: obj.name, status: obj.status, message: msg});
        
        // Show detailed stage information if available
        if (obj.slide_details && Array.isArray(obj.slide_details)) {
          for (const slide of obj.slide_details.slice(0, 3)) {  // Show first 3 slides
            appendLog({
              type: 'log', 
              message: `  Slide ${slide.index}: "${slide.title}" (${slide.purpose}) - ${slide.bullet_count} bullets`
            });
          }
          if (obj.slide_details.length > 3) {
            appendLog({type: 'log', message: `  ... and ${obj.slide_details.length - 3} more slides`});
          }
        }
        
        if (obj.image_details && Array.isArray(obj.image_details)) {
          for (const img of obj.image_details.slice(0, 3)) {  // Show first 3 images
            appendLog({
              type: 'log',
              message: `  Image for slide ${img.slide}: ${img.prompt}`
            });
          }
          if (obj.image_details.length > 3) {
            appendLog({type: 'log', message: `  ... and ${obj.image_details.length - 3} more images`});
          }
        }
        
        if (obj.failure_details && Array.isArray(obj.failure_details)) {
          for (const failure of obj.failure_details) {
            appendLog({
              type: 'log',
              message: `  ❌ ${failure.criterion}: ${failure.reason} (${failure.severity})`
            });
          }
        }
        
        if (obj.name === 'verify' && obj.status === 'DONE') {
          const hard = Array.isArray(obj.hard) ? obj.hard : [];
          const soft = Array.isArray(obj.soft) ? obj.soft : [];
          qcResults = [...hard, ...soft];
        }
      } else if (obj.type === 'agent') {
        const msg = formatAgentMessage(obj);
        appendLog({type: 'log', role: obj.role, stage: obj.stage, event: obj.event, status: obj.status, message: msg});
        
        // Show agent-specific details
        if (obj.slide_titles && Array.isArray(obj.slide_titles)) {
          appendLog({
            type: 'log',
            message: `  📝 Slides: ${obj.slide_titles.join(', ')}`
          });
        }
        
        if (obj.slide_purposes && typeof obj.slide_purposes === 'object') {
          const purposes = Object.entries(obj.slide_purposes).map(([type, count]) => `${count} ${type}`).join(', ');
          appendLog({
            type: 'log',
            message: `  📊 Types: ${purposes}`
          });
        }
        
        if (obj.fonts && typeof obj.fonts === 'object') {
          const fontInfo = Object.entries(obj.fonts).map(([key, value]) => `${key}: ${value}`).join(', ');
          appendLog({
            type: 'log',
            message: `  🎨 Fonts: ${fontInfo}`
          });
        }
        
        if (obj.image_details && Array.isArray(obj.image_details)) {
          for (const img of obj.image_details.slice(0, 2)) {
            appendLog({
              type: 'log',
              message: `  🖼️ Slide ${img.slide}: ${img.prompt}`
            });
          }
        }
        
        if (obj.role === 'orchestrator' && obj.stage === 'complete' && obj.findings) {
          const hard = Array.isArray(obj.findings.qc_hard) ? obj.findings.qc_hard : [];
          const soft = Array.isArray(obj.findings.qc_soft) ? obj.findings.qc_soft : [];
          qcResults = [...hard, ...soft];
        }
      } else if (obj.type === 'error') {
        const msg = isNoisePayload(obj.message) ? 'unknown error' : obj.message;
        appendLog({type: 'log', message: `Error: ${msg}`});
      } else if (obj.type === 'user_input_needed') {
        userInputNeeded = true;
        failedCriteria = obj.failed_criteria || [];
        runIdForContinue = obj.run_id;
        skipChoices = {};
        failedCriteria.forEach(fc => { skipChoices[fc.criterion] = false; });
        running = false;
        appendLog({type: 'log', message: obj.message && !isNoisePayload(obj.message) ? obj.message : 'User input needed.'});
        es?.close();
        es = null;
      } else if (obj.type === 'done') {
        if (obj.success) {
          qcResults = obj.qc_results || qcResults;
          pptDownloadHref = fileUrl();
        } else {
          errorMsg = obj.error || 'Generation failed';
        }
        appendLog({type: 'log', message: 'Run finished.'});
        running = false;
        es?.close();
        es = null;
      }
    } catch (e) {
      // Ignore non-JSON stray payloads
      return;
    }
  }

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
  es.onmessage = handleSSEMessage;
      es.onerror = (e) => {
        appendLog({type: 'log', message: 'Stream error or closed.'});
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
          es.onmessage = handleSSEMessage;
          es.onerror = (e) => {
            appendLog({type: 'log', message: 'Stream error or closed.'});
            running = false;
            es?.close();
            es = null;
          };
        } catch (err) {
          continueError = toErrorMessage(err);
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
  <label class="block text-sm text-white/90" for="topic-input">Topic</label>
  <input id="topic-input" class="w-full rounded p-2 bg-white/10 text-white border border-white/20" bind:value={topic} placeholder="Topic (e.g., GenAI market landscape)" />
  <label class="block mt-3 text-sm text-white/90" for="criteria-input">Criteria</label>
  <textarea id="criteria-input" class="w-full rounded p-2 h-28 bg-white/10 text-white border border-white/20" bind:value={criteriaText} placeholder="Criteria (comma-separated)"></textarea>
  <label class="block mt-3 text-sm text-white/90" for="context-input">Optional context</label>
  <input id="context-input" class="w-full rounded p-2 bg-white/10 text-white border border-white/20" bind:value={context} placeholder="Optional context (persona/style/etc.)" />
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
  <label class="block text-sm text-white/90" for="logpane">Agno Log / Live Output</label>
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
