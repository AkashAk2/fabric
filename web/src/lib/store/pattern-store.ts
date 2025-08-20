import { createStorageAPI } from '$lib/api/base';
import type { Pattern, PatternDescription } from '$lib/interfaces/pattern-interface';
import { get, writable, derived } from 'svelte/store';
import { languageStore } from './language-store';
import { config } from '$lib/config/environment';

// Store for all patterns
const allPatterns = writable<Pattern[]>([]);

// Filtered patterns based on language
export const patterns = derived(
  [allPatterns, languageStore],
  ([$allPatterns, $language]) => {
    if (!$language) return $allPatterns;
    // If language is selected, filter out patterns of other languages
    return $allPatterns.filter(p => {
      // Keep all patterns if no language is selected
      if (!$language) return true;

      // Check if pattern has a language prefix (e.g., en_, fr_)
      const match = p.Name.match(/^([a-z]{2})_/);
      if (!match) return true; // Keep patterns without language prefix

      // Only filter out patterns that have a different language prefix
      const patternLang = match[1];
      return patternLang === $language;
    });
  }
);

export const systemPrompt = writable<string>('');
export const selectedPatternName = writable<string>('');

// Pattern variables store
export const patternVariables = writable<Record<string, string>>({});

export const setSystemPrompt = (prompt: string) => {
  console.log('Setting system prompt:', prompt);
  systemPrompt.set(prompt);
  console.log('Current system prompt:', get(systemPrompt));
};

export const patternAPI = {
  ...createStorageAPI<Pattern>('patterns'),
  
  async loadPatterns() {
  try {
    // First load pattern descriptions
    const descriptionsResponse = await fetch('/data/pattern_descriptions.json');
    const descriptionsData = await descriptionsResponse.json();
    const descriptions = descriptionsData.patterns as PatternDescription[];
    console.log("Loaded pattern descriptions:", descriptions.length);

    // Then load pattern names and contents
    const response = await fetch(`/api/patterns/names`);
    const data = await response.json();
    console.log("Load Patterns:", data);
    console.log("Loading patterns from API...");

    // Create an array of promises to fetch all pattern contents
    const patternsPromises = data.map(async (pattern: string) => {
      try {
        console.log(`Loading pattern: ${pattern}`);
        const patternResponse = await fetch(`/api/patterns/${pattern}`);
        const patternData = await patternResponse.json();
        console.log(`Pattern ${pattern} content length:`, patternData.Pattern?.length || 0);

        // Parse Pattern content if it's JSON string of the whole object
        let patternContent = patternData.Pattern || "";
        try {
          const parsed = JSON.parse(patternContent);
          if (parsed && typeof parsed === 'object' && typeof parsed.Pattern === 'string') {
            patternContent = parsed.Pattern;
          }
        } catch {
          // Not JSON, so ignore parsing error
        }

        // Find matching description from JSON
        const desc = descriptions.find(d => d.patternName === pattern);
        if (!desc) {
          console.warn(`No description found for pattern: ${pattern}`);
        }

        return {
          Name: pattern,
          Description: desc?.description || pattern.charAt(0).toUpperCase() + pattern.slice(1),
          Pattern: patternContent,
          tags: desc?.tags || []  // Add tags from description
        };
      } catch (error) {
        console.error(`Failed to load pattern ${pattern}:`, error);
        // Still try to get description even if pattern content fails
        const desc = descriptions.find(d => d.patternName === pattern);
        return {
          Name: pattern,
          Description: desc?.description || pattern.charAt(0).toUpperCase() + pattern.slice(1),
          Pattern: "",
          tags: desc?.tags || []  // Add tags here too for consistency
        };
      }
    });

    // Wait for all pattern contents to be fetched
    const loadedPatterns = await Promise.all(patternsPromises);
    console.log("Patterns with content:", loadedPatterns);
    allPatterns.set(loadedPatterns);
    return loadedPatterns;
  } catch (error) {
    console.error('Failed to load patterns:', error);
    allPatterns.set([]);
    return [];
  }
},


  selectPattern(patternName: string) {
    const patterns = get(allPatterns);
    console.log('Selecting pattern:', patternName);
    const selectedPattern = patterns.find(p => p.Name === patternName);
    console.log('Selected pattern object:', selectedPattern);
    if (selectedPattern) {
      console.log('Found pattern content (length: ' + selectedPattern.Pattern.length + '):', selectedPattern.Pattern);
      setSystemPrompt(selectedPattern.Pattern);
      selectedPatternName.set(patternName);
    } else {
      console.log('No pattern found for name:', patternName);
      setSystemPrompt('');
      selectedPatternName.set('');
    }
    console.log('System prompt store value after setting:', get(systemPrompt));
  },

  // NEW createPattern API method
  async createPattern(newPattern: { name: string; description: string; tags: string[], pattern?: string }) {
  try {
    const patternObj: Pattern = {
      Name: newPattern.name,
      Description: newPattern.description,
      tags: newPattern.tags,
      Pattern: newPattern.pattern || "",
    };

    console.log('Saving pattern with Pattern field:', patternObj.Pattern);

    await this.save(patternObj.Name, patternObj);
    await this.loadPatterns();

    console.log('Pattern created successfully:', patternObj);
    return patternObj;
  } catch (error) {
    console.error('Failed to create pattern:', error);
    throw error;
  }
},

async save(name: string, patternObj: Pattern) {
  try {
  // Use configured Fabric API URL so production builds call the correct backend host
  const baseApi = config.fabricApiUrl.replace(/\/$/, '');
  const url = `${baseApi}/patterns/${encodeURIComponent(name)}`;
  const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ Pattern: patternObj.Pattern }),
    });


    if (!response.ok) {
      throw new Error(`Failed to save pattern. Status: ${response.status}`);
    }

    console.log('Pattern saved to filesystem.');
  } catch (error) {
    console.error('Error saving pattern:', error);
  }
}



};
