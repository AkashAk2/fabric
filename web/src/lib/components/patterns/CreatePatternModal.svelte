<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { patternAPI } from '$lib/store/pattern-store';
  import { Button } from '$lib/components/ui/button';
  import { Input } from '$lib/components/ui/input';
  import { Label } from '$lib/components/ui/label';
  import { Textarea } from '$lib/components/ui/textarea';
  import { tick } from 'svelte';

  let name = '';
  let description = '';
  let tagsInput = '';
  let patternContent = '';
  let errorMessage = '';
  let successMessage = '';
  let isSubmitting = false;

  const dispatch = createEventDispatcher();

  async function createPattern() {
    errorMessage = '';
    successMessage = '';

    if (!name.trim() || !patternContent.trim()) {
      errorMessage = 'Please fill in all required fields.';
      return;
    }

    isSubmitting = true;

    try {
      const tags = tagsInput
        .split(',')
        .map(tag => tag.trim())
        .filter(tag => tag.length > 0);

      await patternAPI.createPattern({
        name,
        description,
        tags,
        pattern: patternContent
      });

      successMessage = 'Pattern created successfully! Closing modal...';

      // Reset form
      name = '';
      description = '';
      tagsInput = '';
      patternContent = '';

      await tick();
      setTimeout(() => {
        dispatch('close');
      }, 1500);

    } catch (error) {
      errorMessage = 'Failed to create pattern. Check console for details.';
      console.error(error);
    } finally {
      isSubmitting = false;
    }
  }

  function closeModal() {
    dispatch('close');
  }
</script>

<div class="fixed inset-0 bg-black bg-opacity-60 flex items-center justify-center z-50">
  <div class="bg-primary-800/30 rounded-xl shadow-lg p-6 w-full max-w-lg max-h-[90vh] overflow-auto text-white">
    <h2 class="text-xl font-semibold mb-6">Create New Pattern</h2>

    {#if errorMessage}
      <div class="text-red-500 text-sm mb-4">{errorMessage}</div>
    {/if}
    {#if successMessage}
      <div class="text-green-400 text-sm mb-4">{successMessage}</div>
    {/if}

    <div class="space-y-5">
      <div>
        <Label for="pattern-name" class="text-white/80">
          Name <span class="text-red-500">*</span>
        </Label>
        <Input
          id="pattern-name"
          type="text"
          bind:value={name}
          placeholder="Enter pattern name"
          disabled={isSubmitting}
          class="bg-primary-900/50 text-white placeholder:text-white/50 border border-white/20 focus:border-blue-400"
        />
      </div>

      <div>
        <Label for="pattern-description" class="text-white/80">Description</Label>
        <Textarea
          id="pattern-description"
          bind:value={description}
          placeholder="Optional description"
          rows="3"
          disabled={isSubmitting}
          class="bg-primary-900/50 text-white placeholder:text-white/50 border border-white/20 focus:border-blue-400"
        />
      </div>

      <div>
        <Label for="pattern-tags" class="text-white/80">Tags (comma separated)</Label>
        <Input
          id="pattern-tags"
          type="text"
          bind:value={tagsInput}
          placeholder="e.g. chatbot, automation"
          disabled={isSubmitting}
          class="bg-primary-900/50 text-white placeholder:text-white/50 border border-white/20 focus:border-blue-400"
        />
      </div>

      <div>
        <Label for="pattern-content" class="text-white/80">
          Pattern Content (System Prompt) <span class="text-red-500">*</span>
        </Label>
        <Textarea
          id="pattern-content"
          bind:value={patternContent}
          rows="6"
          placeholder="Enter your system prompt or pattern logic here"
          disabled={isSubmitting}
          class="font-mono text-sm bg-primary-900/50 text-white placeholder:text-white/50 border border-white/20 focus:border-blue-400"
        />
      </div>
    </div>

    <div class="flex justify-end mt-8 space-x-3">
      <Button
        variant="outline"
        on:click={closeModal}
        disabled={isSubmitting}
        class="border text-white border-white/40 hover:border-white/60"
      >
        Cancel
      </Button>
      <Button
        on:click={createPattern}
        disabled={isSubmitting}
        class="border text-white border-white/40 hover:border-white/60"
      >
        {isSubmitting ? 'Creating...' : 'Create'}
      </Button>
    </div>
  </div>
</div>

<style>
  textarea::-webkit-scrollbar {
    width: 8px;
  }
  textarea::-webkit-scrollbar-thumb {
    background-color: rgba(255, 255, 255, 0.2);
    border-radius: 4px;
  }
</style>
