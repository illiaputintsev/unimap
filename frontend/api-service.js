/**
 * API Service for StudentRoadmap Backend
 * Handles all communication with the backend API
 */

const DEFAULT_API_BASE_URL = 'https://studentroadmap-api-m5hqauiyxa-nw.a.run.app';
const LOCAL_PROXY_URL = 'http://127.0.0.1:8081';
const apiBaseOverride = typeof window !== 'undefined'
  ? localStorage.getItem('apiBaseUrl')
  : null;
const API_BASE_URL = apiBaseOverride || DEFAULT_API_BASE_URL;
const TOKEN_KEY = 'access_token';
const REFRESH_TOKEN_KEY = 'refresh_token';
const LEGACY_TOKEN_KEY = 'authToken';
const LEGACY_REFRESH_TOKEN_KEY = 'refreshToken';

class ApiService {
  static getAccessToken() {
    return localStorage.getItem(TOKEN_KEY) || localStorage.getItem(LEGACY_TOKEN_KEY) || '';
  }

  static getRefreshToken() {
    return localStorage.getItem(REFRESH_TOKEN_KEY) || localStorage.getItem(LEGACY_REFRESH_TOKEN_KEY) || '';
  }

  static decodeJwtPayload(token) {
    try {
      const parts = token.split('.');
      if (parts.length < 2) return null;
      const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
      const padded = base64.padEnd(base64.length + (4 - (base64.length % 4 || 4)) % 4, '=');
      return JSON.parse(atob(padded));
    } catch {
      return null;
    }
  }

  static isTokenExpired(token, leewaySeconds = 30) {
    const payload = this.decodeJwtPayload(token);
    if (!payload || !payload.exp) return false;
    const now = Math.floor(Date.now() / 1000);
    return payload.exp <= (now + leewaySeconds);
  }

  static async ensureValidAccessToken() {
    const accessToken = this.getAccessToken();
    if (accessToken && !this.isTokenExpired(accessToken)) {
      if (!localStorage.getItem(TOKEN_KEY)) {
        localStorage.setItem(TOKEN_KEY, accessToken);
      }
      return true;
    }

    const refreshToken = this.getRefreshToken();
    if (!refreshToken) return false;
    return this.refreshToken();
  }

  static _buildUrl(endpoint) {
    const base = API_BASE_URL.replace(/\/+$/, '');
    const path = String(endpoint || '').replace(/^\/+/, '');
    return `${base}/${path}`;
  }

  /**
   * Make an authenticated API request with automatic token refresh
   */
  static async request(endpoint, options = {}) {
    if (!options.noAuth) {
      await this.ensureValidAccessToken();
    }

    let response = await this._makeRequest(endpoint, options);
    
    // If unauthorized, try to refresh token and retry once
    if (response.status === 401 && !options.noAuth && options.retry !== false) {
      const refreshed = await this.refreshToken();
      if (refreshed) {
        options.retry = false; // Prevent infinite loop
        response = await this._makeRequest(endpoint, options);
      }
    }
    
    return response;
  }

  /**
   * Internal method to make the actual HTTP request
   */
  static async _makeRequest(endpoint, options = {}) {
    const url = this._buildUrl(endpoint);
    const isFormData = typeof FormData !== 'undefined' && options.formData instanceof FormData;
    const config = {
      method: options.method || 'GET',
      headers: {
        ...options.headers
      }
    };

    if (!isFormData) {
      config.headers['Content-Type'] = config.headers['Content-Type'] || 'application/json';
    }

    // Add authorization header if token exists
    const token = this.getAccessToken();
    if (token && !options.noAuth) {
      config.headers['Authorization'] = `Bearer ${token}`;
    }

    // Add body for POST, PATCH, PUT
    if (isFormData) {
      config.body = options.formData;
      delete config.headers['Content-Type']; // Let browser set multipart boundary
    } else if (options.body) {
      config.body = JSON.stringify(options.body);
    }

    try {
      const response = await fetch(url, config);
      const data = await response.json().catch(() => ({}));
      return { status: response.status, data, ok: response.ok };
    } catch (error) {
      console.error('API Request Error:', error);
      return { status: 0, data: { error: error.message }, ok: false };
    }
  }

  // ==================== AUTH ENDPOINTS ====================

  /**
   * Register a new user
   * POST /api/auth/register/
   */
  static async register(username, email, password) {
    const response = await this._makeRequest('api/auth/register/', {
      method: 'POST',
      body: { username, email, password },
      noAuth: true
    });
    return response;
  }

  /**
   * Get JWT token pair
   * POST /api/auth/token/
   */
  static async login(username, password) {
    const response = await this._makeRequest('api/auth/token/', {
      method: 'POST',
      body: { username, password },
      noAuth: true
    });

    if (response.ok && response.data.access) {
      localStorage.setItem(TOKEN_KEY, response.data.access);
      localStorage.setItem(REFRESH_TOKEN_KEY, response.data.refresh);
      localStorage.setItem(LEGACY_TOKEN_KEY, response.data.access);
      localStorage.setItem(LEGACY_REFRESH_TOKEN_KEY, response.data.refresh);
    }

    return response;
  }

  /**
   * Refresh access token
   * POST /api/auth/token/refresh/
   */
  static async refreshToken() {
    const refreshToken = this.getRefreshToken();
    if (!refreshToken) return false;

    const response = await this._makeRequest('api/auth/token/refresh/', {
      method: 'POST',
      body: { refresh: refreshToken },
      noAuth: true
    });

    if (response.ok && response.data.access) {
      localStorage.setItem(TOKEN_KEY, response.data.access);
      localStorage.setItem(LEGACY_TOKEN_KEY, response.data.access);
      return true;
    }

    // Refresh failed, clear tokens
    this.logout();
    return false;
  }

  /**
   * Logout - clear stored tokens
   */
  static logout() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    localStorage.removeItem(LEGACY_TOKEN_KEY);
    localStorage.removeItem(LEGACY_REFRESH_TOKEN_KEY);
  }

  /**
   * Check if user is authenticated
   */
  static isAuthenticated() {
    return !!this.getAccessToken() || !!this.getRefreshToken();
  }

  // ==================== CATALOG ENDPOINTS ====================

  /**
   * Search universities
   * GET /api/catalog/universities/?q=<query>
   */
  static async searchUniversities(query) {
    const response = await this.request(
      `api/catalog/universities/?q=${encodeURIComponent(query)}`,
      { noAuth: true }
    );
    return response;
  }

  /**
   * Search courses
   * GET /api/catalog/courses/?university_id=<id>&q=<query>
   */
  static async searchCourses(universityId, query) {
    const response = await this.request(
      `api/catalog/courses/?university_id=${universityId}&q=${encodeURIComponent(query)}`,
      { noAuth: true }
    );
    return response;
  }

  /**
   * Generate module draft for selected course
   * POST /api/catalog/courses/{course_id}/modules/draft/
   */
  static async generateModuleDraft(courseId, options = {}) {
    const body = {
      refresh: options.refresh !== undefined ? options.refresh : true,
      insecure: options.insecure !== undefined ? options.insecure : true,
      timeout: options.timeout || 15,
      context_text: options.contextText || '',
      use_ai: options.useAi !== false // default true
    };

    const response = await this.request(
      `api/catalog/courses/${courseId}/modules/draft/`,
      { method: 'POST', body }
    );
    return response;
  }

  /**
   * Confirm final modules (user-edited)
   * POST /api/catalog/courses/{course_id}/modules/confirm/
   */
  static async confirmModules(courseId, modules) {
    const response = await this.request(
      `api/catalog/courses/${courseId}/modules/confirm/`,
      { method: 'POST', body: { modules } }
    );
    return response;
  }

  // ==================== ROADMAP ENDPOINTS ====================

  /**
   * Generate a new roadmap
   * POST /api/roadmaps/generate/
   */
  static async generateRoadmap(data) {
    // data can include:
    // - title, course_id, career_goal (UK/discovered course)
    // - manual_course_title, module_names, career_goal (manual/non-UK)
    const response = await this.request(
      'api/roadmaps/generate/',
      { method: 'POST', body: data }
    );
    return response;
  }

  /**
   * List user's roadmaps
   * GET /api/roadmaps/
   */
  static async listRoadmaps() {
    const response = await this.request('api/roadmaps/');
    return response;
  }

  /**
   * Get roadmap details
   * GET /api/roadmaps/{roadmap_id}/
   */
  static async getRoadmap(roadmapId) {
    const response = await this.request(`api/roadmaps/${roadmapId}/`);
    return response;
  }

  /**
   * Delete roadmap
   * DELETE /api/roadmaps/{roadmap_id}/
   */
  static async deleteRoadmap(roadmapId) {
    const response = await this.request(`api/roadmaps/${roadmapId}/`, {
      method: 'DELETE'
    });
    return response;
  }

  /**
   * Update topic progress
   * PATCH /api/roadmaps/topics/{topic_id}/progress/
   */
  static async updateTopicProgress(topicId, masteryPercent) {
    const response = await this.request(
      `api/roadmaps/topics/${topicId}/progress/`,
      { method: 'PATCH', body: { mastery_percent: masteryPercent } }
    );
    return response;
  }

  // ==================== GRAPH ENDPOINTS ====================

  /**
   * Build course modules graph adjacency matrix
   * POST /api/catalog/courses/{course_id}/modules/graph/
   */
  static async generateCourseModulesGraph(courseId, options = {}) {
    const body = {
      modules: options.modules,
      threshold: options.threshold,
      max_outgoing: options.maxOutgoing,
      use_ai: options.useAi !== false,
      use_draft_fallback: options.useDraftFallback !== false,
      ai_timeout: options.aiTimeout || 60
    };

    // Remove undefined fields to keep payload clean
    Object.keys(body).forEach((key) => {
      if (body[key] === undefined) delete body[key];
    });

    const response = await this.request(
      `api/catalog/courses/${courseId}/modules/graph/`,
      { method: 'POST', body }
    );
    return response;
  }

  /**
   * Get persisted roadmap graph
   * GET /api/roadmaps/{roadmap_id}/graph/
   */
  static async getRoadmapGraph(roadmapId) {
    const response = await this.request(`api/roadmaps/${roadmapId}/graph/`);
    return response;
  }

  /**
   * Get roadmap graph summary
   * GET /api/roadmaps/{roadmap_id}/graph/summary/
   */
  static async getRoadmapGraphSummary(roadmapId) {
    const response = await this.request(`api/roadmaps/${roadmapId}/graph/summary/`);
    return response;
  }

  /**
   * Update topic progress via graph endpoint
   * PATCH /api/roadmaps/{roadmap_id}/graph/topics/{topic_id}/progress/
   */
  static async updateRoadmapGraphTopicProgress(roadmapId, topicId, masteryPercent) {
    const response = await this.request(
      `api/roadmaps/${roadmapId}/graph/topics/${topicId}/progress/`,
      { method: 'PATCH', body: { mastery_percent: masteryPercent } }
    );
    return response;
  }

  // ==================== QUIZ / MODULE WORKSPACE ENDPOINTS ====================

  /**
   * Generate personalized module topics (Gemini-backed with backend fallback)
   * POST /api/quizzes/module-topics/generate/
   */
  static async generateModuleTopics(payload) {
    return this.request('api/quizzes/module-topics/generate/', {
      method: 'POST',
      body: payload || {}
    });
  }

  /**
   * Generate personalized module quiz (Gemini-backed with backend fallback)
   * POST /api/quizzes/module-quiz/generate/
   */
  static async generateModuleQuiz(payload) {
    return this.request('api/quizzes/module-quiz/generate/', {
      method: 'POST',
      body: payload || {}
    });
  }

  /**
   * List stored module notes (PDF uploads)
   * GET /api/quizzes/module-notes/?module_id=...&roadmap_id=...
   */
  static async listModuleNotes({ moduleId, roadmapId } = {}) {
    const params = new URLSearchParams();
    if (moduleId !== undefined && moduleId !== null) params.set('module_id', String(moduleId));
    if (roadmapId !== undefined && roadmapId !== null && roadmapId !== '') params.set('roadmap_id', String(roadmapId));
    const qs = params.toString();
    return this.request(`api/quizzes/module-notes/${qs ? `?${qs}` : ''}`);
  }

  /**
   * Upload a module note PDF + extracted text metadata
   * POST /api/quizzes/module-notes/
   */
  static async uploadModuleNote(formData) {
    return this.request('api/quizzes/module-notes/', {
      method: 'POST',
      formData
    });
  }

  /**
   * Delete stored module note
   * DELETE /api/quizzes/module-notes/{id}/
   */
  static async deleteModuleNote(noteId) {
    return this.request(`api/quizzes/module-notes/${noteId}/`, {
      method: 'DELETE'
    });
  }

  // ==================== HELPER METHODS ====================

  /**
   * Get current user from localStorage
   */
  static getCurrentUser() {
    return {
      token: localStorage.getItem(TOKEN_KEY),
      isAuthenticated: this.isAuthenticated()
    };
  }

  /**
   * Handle API errors in a user-friendly way
   */
  static getErrorMessage(response) {
    if (!response.ok) {
      // Check for specific error codes
      if (response.status === 429) {
        return 'Server quota exceeded. Please try again later.';
      }
      if (response.status === 503) {
        return 'Service unavailable. Please try again later.';
      }
      if (response.status === 401) {
        return 'Session expired or unauthorized. Please login again.';
      }
      if (response.status === 400) {
        if (typeof response.data?.detail === 'string') {
          return response.data.detail;
        }
        if (Array.isArray(response.data?.detail)) {
          return response.data.detail.join(', ');
        }
        if (response.data && typeof response.data === 'object') {
          const fieldErrors = [];
          for (const [field, messages] of Object.entries(response.data)) {
            if (Array.isArray(messages)) {
              fieldErrors.push(`${field}: ${messages.join(', ')}`);
            } else if (typeof messages === 'string') {
              fieldErrors.push(`${field}: ${messages}`);
            }
          }
          if (fieldErrors.length > 0) {
            return fieldErrors.join(' | ');
          }
        }
        return 'Invalid request. Please check your input.';
      }
      if (response.data.error) {
        return response.data.error;
      }
    }
    return 'An error occurred. Please try again.';
  }
}

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
  module.exports = ApiService;
}

if (typeof window !== 'undefined') {
  window.ApiService = ApiService;
}
