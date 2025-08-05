import { createStorageAPI } from '$lib/api/base';
import type { Pattern, PatternDescription } from '$lib/interfaces/pattern-interface';
import { get, writable, derived } from 'svelte/store';
import { languageStore } from './language-store';

// Store for all patterns
const allPatterns = writable<Pattern[]>([]);

// Filtered patterns based on language
export const patterns = derived(
  [allPatterns, languageStore],
  ([$allPatterns, $language]) => {
    if (!$language) return $allPatterns;

    return $allPatterns.filter(p => {
      const match = p.Name.match(/^([a-z]{2})_/);
      if (!match) return true;
      const patternLang = match[1];
      return patternLang === $language;
    });
  }
);

export const systemPrompt = writable<string>('');
export const selectedPatternName = writable<string>('');
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
      const descriptionsResponse = await fetch('/data/pattern_descriptions.json');
      const descriptionsData = await descriptionsResponse.json();
      const descriptions = descriptionsData.patterns as PatternDescription[];

      const response = await fetch(`/api/patterns/names`);
      const data = await response.json();

      const patternsPromises = data.map(async (pattern: string) => {
        try {
          const patternResponse = await fetch(`/api/patterns/${pattern}`);
          const patternData = await patternResponse.json();

          const desc = descriptions.find(d => d.patternName === pattern);
          return {
            Name: pattern,
            Description: desc?.description || pattern,
            Pattern: patternData.Pattern || '',
            tags: desc?.tags || []
          };
        } catch (error) {
          console.error(`Failed to load pattern ${pattern}:`, error);
          const desc = descriptions.find(d => d.patternName === pattern);
          return {
            Name: pattern,
            Description: desc?.description || pattern,
            Pattern: '',
            tags: desc?.tags || []
          };
        }
      });

      const loadedPatterns = await Promise.all(patternsPromises);
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

  async createPattern(newPattern: {
    name: string;
    description: string;
    tags: string[];
    pattern?: string;
  }) {
    try {
      const patternObj: Pattern = {
        Name: newPattern.name,
        Description: newPattern.description,
        tags: newPattern.tags,
        Pattern: newPattern.pattern || '',
      };

      await this.save(patternObj.Name, patternObj);
      await this.loadPatterns();
      console.log('Pattern created successfully:', patternObj);
      return patternObj;
    } catch (error) {
      console.error('Failed to create pattern:', error);
      throw error;
    }
  }
};
