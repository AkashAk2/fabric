<script lang="ts">
  import { page } from '$app/stores';
  import { Sun, Moon, Menu, X, Github, FileText, Plus } from 'lucide-svelte';
  import { Avatar } from '@skeletonlabs/skeleton';
  import { fade } from 'svelte/transition';
  import { theme, cycleTheme, initTheme } from '$lib/store/theme-store';
  import { onMount } from 'svelte';
  import Modal from '$lib/components/ui/modal/Modal.svelte';
  import PatternList from '$lib/components/patterns/PatternList.svelte';
  import PatternTilesModal from '$lib/components/ui/modal/PatternTilesModal.svelte';
  import CreatePatternModal from '$lib/components/patterns/CreatePatternModal.svelte';
  import HelpModal from '$lib/components/ui/help/HelpModal.svelte';
  import { selectedPatternName } from '$lib/store/pattern-store';

  let isMenuOpen = false;
  let showPatternModal = false;
  let showPatternTilesModal = false;
  let showHelpModal = false;
  let showCreatePatternModal = false;

  function goToGithub() {
    window.open('https://github.com/danielmiessler/fabric', '_blank');
  }

  function toggleMenu() {
    isMenuOpen = !isMenuOpen;
  }

  $: currentPath = $page.url.pathname;
  $: isDarkMode = $theme === 'my-custom-theme';

  const navItems = [
    { href: '/', label: 'Home' },
    { href: '/posts', label: 'Posts' },
    { href: '/chat', label: 'Chat' },
    { href: '/contact', label: 'Contact' },
    { href: '/about', label: 'About' },
  ];

  onMount(() => {
    initTheme();
  });
</script>

<header class="fixed top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
  <div class="container flex h-16 items-center justify-between px-4">
    <div class="flex items-center gap-4">
      <Avatar src="/fabric-logo.png" width="w-10" rounded="rounded-full" class="border-2 border-primary/20" />
      <a href="/" class="flex items-center">
        <span class="text-lg font-semibold">fabric</span>
      </a>
    </div>

    <!-- Desktop Navigation -->
    <nav class="hidden flex-1 px-8 md:flex">
      <ul class="flex items-center space-x-8">
        {#each navItems as { href, label }}
          <li>
            <a
              {href}
              class="text-sm font-medium transition-colors hover:text-primary {currentPath === href ? 'text-primary' : 'text-foreground/60'}"
            >
              {label}
            </a>
          </li>
        {/each}
      </ul>
    </nav>

    <div class="flex items-center gap-4">
      <!-- Pattern Buttons Group -->
      <div class="flex items-center gap-3 mr-4">
        <button
          name="pattern-tiles"
          on:click={() => showPatternTilesModal = true}
          class="inline-flex h-10 items-center justify-center rounded-full border bg-background px-4 text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground gap-2"
          aria-label="Pattern Tiles"
        >
          <FileText class="h-4 w-4" />
          <span>Pattern Tiles</span>
        </button>

        <button
          name="pattern-list"
          on:click={() => showPatternModal = true}
          class="inline-flex h-10 items-center justify-center rounded-full border bg-background px-4 text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground gap-2"
          aria-label="Pattern List"
        >
          <FileText class="h-4 w-4" />
          <span>Pattern List</span>
        </button>
      </div>

      <!-- Create Pattern Button -->
      <button
        name="create-pattern"
        on:click={() => showCreatePatternModal = true}
        class="inline-flex h-10 items-center justify-center rounded-full border bg-primary/80 px-4 text-sm font-medium transition-colors text-white hover:bg-primary/90 gap-2"
        aria-label="Create Pattern"
      >
        <Plus class="h-4 w-4" />
        <span>Create Pattern</span>
      </button>

      <!-- GitHub -->
      <button
        name="github"
        on:click={goToGithub}
        class="inline-flex h-9 w-9 items-center justify-center rounded-full border bg-background transition-colors hover:bg-accent hover:text-accent-foreground"
        aria-label="GitHub"
      >
        <Github class="h-4 w-4" />
      </button>

      <!-- Theme Toggle -->
      <button
        name="toggle-theme"
        on:click={cycleTheme}
        class="inline-flex h-9 w-9 items-center justify-center rounded-full border bg-background transition-colors hover:bg-accent hover:text-accent-foreground"
        aria-label="Toggle theme"
      >
        {#if isDarkMode}
          <Sun class="h-4 w-4" />
        {:else}
          <Moon class="h-4 w-4" />
        {/if}
      </button>

      <!-- Help -->
      <button
        name="help"
        on:click={() => showHelpModal = true}
        class="inline-flex h-9 w-9 items-center justify-center rounded-full border bg-background transition-colors hover:bg-accent hover:text-accent-foreground ml-3"
        aria-label="Help"
      >
        <span class="text-xl font-bold text-white/90 hover:text-white">?</span>
      </button>

      <!-- Mobile Menu Button -->
      <button
        name="toggle-menu"
        on:click={toggleMenu}
        class="inline-flex h-9 w-9 items-center justify-center rounded-lg border bg-background md:hidden transition-colors hover:bg-accent hover:text-accent-foreground"
        aria-expanded={isMenuOpen}
        aria-label="Toggle menu"
      >
        {#if isMenuOpen}
          <X class="h-4 w-4" />
        {:else}
          <Menu class="h-4 w-4" />
        {/if}
      </button>
    </div>
  </div>

  <!-- Mobile Navigation -->
  {#if isMenuOpen}
    <div class="container md:hidden" transition:fade={{ duration: 200 }}>
      <nav class="flex flex-col space-y-4 p-4">
        {#each navItems as { href, label }}
          <a
            {href}
            on:click={() => (isMenuOpen = false)}
            class="text-base font-medium transition-colors hover:text-primary {currentPath === href ? 'text-primary' : 'text-foreground/60'}"
          >
            {label}
          </a>
        {/each}
      </nav>
    </div>
  {/if}
</header>

<!-- Pattern List Modal -->
<Modal
  show={showPatternModal}
  on:close={() => showPatternModal = false}
>
  <PatternList
    on:close={() => showPatternModal = false}
    on:select={(e) => {
      selectedPatternName.set(e.detail);
      showPatternModal = false;
    }}
  />
</Modal>

<!-- Create Pattern Modal (placeholder - can replace later with dedicated component) -->
<Modal
  show={showCreatePatternModal}
  on:close={() => showCreatePatternModal = false}
>
  <CreatePatternModal
    on:close={() => showCreatePatternModal = false}
    on:success={() => {
      // Optional: You can do something on success, like close modal or reload data
      showCreatePatternModal = false;
      // e.g. refresh patterns if needed
    }}
  />
</Modal>

<!-- Help Modal -->
<Modal
  show={showHelpModal}
  on:close={() => showHelpModal = false}
>
  <HelpModal on:close={() => showHelpModal = false} />
</Modal>

<!-- Pattern Tiles Modal -->
<Modal
  show={showPatternTilesModal}
  on:close={() => showPatternTilesModal = false}
>
  <PatternTilesModal
    on:close={() => showPatternTilesModal = false}
    on:select={(e) => {
      selectedPatternName.set(e.detail);
      showPatternTilesModal = false;
    }}
  />
</Modal>
