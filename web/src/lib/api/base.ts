import type { StorageEntity } from '$lib/interfaces/storage-interface';

interface APIErrorResponse {
  error: string;
}

interface APIResponse<T> {
  data?: T;
  error?: string;
}

// Define and export the base api object
export const api = {
  async fetch<T>(endpoint: string, options: RequestInit = {}): Promise<APIResponse<T>> {
    const response = await fetch(`/api${endpoint}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    });

    if (!response.ok) {
      // try to parse error JSON, fallback to status text if empty or invalid
      let errorMessage = response.statusText;
      try {
        const errorJson = await response.json() as APIErrorResponse;
        if (errorJson?.error) errorMessage = errorJson.error;
      } catch {
        // ignore JSON parse error for error responses
      }
      return { error: errorMessage };
    }

    // Check content-length and content-type before parsing JSON
    const contentLength = response.headers.get('content-length');
    const contentType = response.headers.get('content-type');

    if (contentLength === '0' || !contentType?.includes('application/json')) {
      // No content or not JSON, return empty data
      return { data: undefined };
    }

    // Safe to parse JSON now
    return { data: await response.json() as T };
  },
  
  get: <T>(endpoint: string) => api.fetch<T>(endpoint),
  post: <T>(endpoint: string, data: unknown) => api.fetch<T>(endpoint, { method: 'POST', body: JSON.stringify(data) }),
  put: <T>(endpoint: string, data?: unknown) => api.fetch<T>(endpoint, { method: 'PUT', body: data ? JSON.stringify(data) : undefined }),
  delete: <T>(endpoint: string) => api.fetch<T>(endpoint, { method: 'DELETE' }),

  stream: async function* (endpoint: string, data: unknown): AsyncGenerator<string> {
    const response = await fetch(`/api${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const reader = response.body?.getReader();
    if (!reader) throw new Error('Response body is null');

    const decoder = new TextDecoder();
    while (true) {
      const { done, value } = await reader.read();
      yield decoder.decode(value);

      if (done) break;
    }
  }
};

export function createStorageAPI<T extends StorageEntity>(entityType: string) {
  return {
    async get(name: string): Promise<T> {
      const response = await api.fetch<T>(`/${entityType}/${name}`);
      if (response.error) throw new Error(response.error);
      return response.data as T;
    },

    async getNames(): Promise<string[]> {
      const response = await api.fetch<string[]>(`/${entityType}/names`);
      if (response.error) throw new Error(response.error);
      return response.data as [];
    },

    async delete(name: string): Promise<void> {
      const response = await api.fetch(`/${entityType}/${name}`, { method: 'DELETE' });
      if (response.error) throw new Error(response.error);
    },

    async exists(name: string): Promise<boolean> {
      const response = await api.fetch<boolean>(`/${entityType}/exists/${name}`);
      if (response.error) throw new Error(response.error);
      return response.data as boolean;
    },

    async rename(oldName: string, newName: string): Promise<void> {
      const response = await api.fetch(`/${entityType}/rename/${oldName}/${newName}`, { method: 'PUT' });
      if (response.error) throw new Error(response.error);
    },

    async save(name: string, content: string | object): Promise<void> {
      const response = await api.fetch(`/${entityType}/${name}`, {
        method: 'POST',
        body: JSON.stringify(content),
        headers: { 'Content-Type': 'application/json' },
      });
      if (response.error) throw new Error(response.error);
    },
  };
}
