import axios, { AxiosError } from 'axios'
import type { AxiosInstance } from 'axios'
import type {
  Project,
  ProjectCreate,
  ProjectUpdate,
  ProjectListResponse,
  ProjectStatusUpdate,
  Character,
  CharacterCreate,
  CharacterUpdate,
  CharacterListResponse,
  ShotListResponse,
  Job,
  JobCreate,
  JobListResponse,
  JobProgressUpdate,
  JobStatusUpdate,
  ShotRender,
  ShotRenderListResponse,
  Chapter,
  ChapterCreate,
  ChapterListResponse,
  PipelineStartRequest,
  PipelineStartResponse,
  ErrorResponse,
  ConfigStatusResponse,
  ProviderTestResult,
  AllTestsResponse
} from '@/types/api'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1'

class ApiClient {
  private client: AxiosInstance

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json'
      }
    })

    this.client.interceptors.response.use(
      (response) => response,
      (error: AxiosError<ErrorResponse>) => {
        const errorMessage = error.response?.data?.message || error.message
        return Promise.reject(new Error(errorMessage))
      }
    )
  }

  // 长时间运行操作的超时时间（5分钟）
  private longTimeout = 300000

  // Projects
  async createProject(data: ProjectCreate): Promise<Project> {
    const response = await this.client.post<Project>('/projects', data)
    return response.data
  }

  async listProjects(params?: {
    page?: number
    page_size?: number
    status?: string
  }): Promise<ProjectListResponse> {
    const response = await this.client.get<ProjectListResponse>('/projects', { params })
    return response.data
  }

  async getProject(projectId: string): Promise<Project> {
    const response = await this.client.get<Project>(`/projects/${projectId}`)
    return response.data
  }

  async updateProject(projectId: string, data: ProjectUpdate): Promise<Project> {
    const response = await this.client.patch<Project>(`/projects/${projectId}`, data)
    return response.data
  }

  async deleteProject(projectId: string): Promise<void> {
    await this.client.delete(`/projects/${projectId}`)
  }

  async updateProjectStatus(projectId: string, data: ProjectStatusUpdate): Promise<Project> {
    const response = await this.client.put<Project>(`/projects/${projectId}/status`, data)
    return response.data
  }

  async buildAssets(projectId: string): Promise<{ message: string }> {
    const response = await this.client.post<{ message: string }>(
      `/projects/${projectId}/assets/build`,
      {},
      { timeout: this.longTimeout }
    )
    return response.data
  }

  async generateStoryboard(projectId: string): Promise<ShotListResponse> {
    const response = await this.client.post<ShotListResponse>(
      `/projects/${projectId}/storyboard/generate`,
      {},
      { timeout: this.longTimeout }
    )
    return response.data
  }

  async startPipeline(projectId: string, data?: PipelineStartRequest): Promise<PipelineStartResponse> {
    const response = await this.client.post<PipelineStartResponse>(
      `/projects/${projectId}/pipeline/start`,
      data || { project_id: projectId },
      { timeout: this.longTimeout }
    )
    return response.data
  }

  async listShots(projectId: string): Promise<ShotListResponse> {
    const response = await this.client.get<ShotListResponse>(`/projects/${projectId}/shots`)
    return response.data
  }

  async addChapter(projectId: string, data: ChapterCreate): Promise<Chapter> {
    const response = await this.client.post<Chapter>(`/projects/${projectId}/chapters`, data)
    return response.data
  }

  async listChapters(projectId: string): Promise<ChapterListResponse> {
    const response = await this.client.get<ChapterListResponse>(`/projects/${projectId}/chapters`)
    return response.data
  }

  async getChapter(projectId: string, chapterNumber: number): Promise<Chapter> {
    const response = await this.client.get<Chapter>(
      `/projects/${projectId}/chapters/${chapterNumber}`
    )
    return response.data
  }

  async deleteChapter(projectId: string, chapterNumber: number): Promise<void> {
    await this.client.delete(`/projects/${projectId}/chapters/${chapterNumber}`)
  }

  // Characters
  async createCharacter(data: CharacterCreate, projectId?: string): Promise<Character> {
    const response = await this.client.post<Character>('/assets/characters', data, {
      params: projectId ? { project_id: projectId } : undefined
    })
    return response.data
  }

  async listCharacters(projectId?: string): Promise<CharacterListResponse> {
    const response = await this.client.get<CharacterListResponse>('/assets/characters', {
      params: projectId ? { project_id: projectId } : undefined
    })
    return response.data
  }

  async getCharacter(characterId: string): Promise<Character> {
    const response = await this.client.get<Character>(`/assets/characters/${characterId}`)
    return response.data
  }

  async updateCharacter(characterId: string, data: CharacterUpdate): Promise<Character> {
    const response = await this.client.patch<Character>(`/assets/characters/${characterId}`, data)
    return response.data
  }

  async deleteCharacter(characterId: string): Promise<void> {
    await this.client.delete(`/assets/characters/${characterId}`)
  }

  async generateCharacterReference(characterId: string): Promise<{ message: string; image_path: string }> {
    const response = await this.client.post<{ message: string; image_path: string }>(
      `/assets/characters/${characterId}/generate-reference`
    )
    return response.data
  }

  // Jobs
  async createJob(data: JobCreate): Promise<Job> {
    const response = await this.client.post<Job>('/jobs', data)
    return response.data
  }

  async listJobs(params?: {
    project_id?: string
    job_type?: string
    status?: string
  }): Promise<JobListResponse> {
    const response = await this.client.get<JobListResponse>('/jobs', { params })
    return response.data
  }

  async getJob(jobId: string): Promise<Job> {
    const response = await this.client.get<Job>(`/jobs/${jobId}`)
    return response.data
  }

  async updateJobProgress(jobId: string, data: JobProgressUpdate): Promise<Job> {
    const response = await this.client.put<Job>(`/jobs/${jobId}/progress`, data)
    return response.data
  }

  async updateJobStatus(jobId: string, data: JobStatusUpdate): Promise<Job> {
    const response = await this.client.put<Job>(`/jobs/${jobId}/status`, data)
    return response.data
  }

  async cancelJob(jobId: string): Promise<{ message: string }> {
    const response = await this.client.post<{ message: string }>(`/jobs/${jobId}/cancel`)
    return response.data
  }

  async listShotRenders(jobId: string): Promise<ShotRenderListResponse> {
    const response = await this.client.get<ShotRenderListResponse>(`/jobs/${jobId}/shot-renders`)
    return response.data
  }

  async getShotRender(renderId: string): Promise<ShotRender> {
    const response = await this.client.get<ShotRender>(`/jobs/shot-renders/${renderId}`)
    return response.data
  }

  async retryJob(jobId: string): Promise<Job> {
    const response = await this.client.post<Job>(`/jobs/${jobId}/retry`)
    return response.data
  }

  async retryShotRender(renderId: string): Promise<ShotRender> {
    const response = await this.client.post<ShotRender>(`/jobs/shot-renders/${renderId}/retry`)
    return response.data
  }

  // API Test
  async getApiConfig(): Promise<ConfigStatusResponse> {
    const response = await this.client.get<ConfigStatusResponse>('/api-test/config')
    return response.data
  }

  async testProvider(category: string, provider: string): Promise<ProviderTestResult> {
    const response = await this.client.post<ProviderTestResult>(
      `/api-test/test/${category}/${provider}`,
      {},
      { timeout: 60000 }
    )
    return response.data
  }

  async testAllProviders(): Promise<AllTestsResponse> {
    const response = await this.client.post<AllTestsResponse>(
      '/api-test/test-all',
      {},
      { timeout: 300000 }
    )
    return response.data
  }
}

export const apiClient = new ApiClient()
