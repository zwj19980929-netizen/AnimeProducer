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
  CharacterImage,
  CharacterImageListResponse,
  GenerateVariantRequest,
  BatchGenerateVariantRequest,
  SetAnchorImageRequest,
  MarkTrainingImagesRequest,
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
  ChapterUpdate,
  ChapterListResponse,
  ChapterAnalysisResult,
  ChapterBatchAnalysisResponse,
  Book,
  BookUpdate,
  Episode,
  EpisodeCreate,
  EpisodeUpdate,
  EpisodeListResponse,
  EpisodePlanRequest,
  EpisodePlanResponse,
  PipelineStartRequest,
  PipelineStartResponse,
  ErrorResponse,
  ConfigStatusResponse,
  ProviderTestResult,
  AllTestsResponse,
  VoiceConfig,
  VoicePreviewRequest,
  VoicePreviewResponse,
  AvailableVoicesResponse,
  LoRAStartTrainingRequest,
  LoRAStartTrainingJobResponse,
  CharacterLoRA,
  LoRATrainingStatusResponse,
  LoRAListResponse,
  ProviderStatusResponse,
  LoginRequest,
  RegisterRequest,
  Token,
  User,
  GenerateReferenceJobResponse
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

  async buildAssetsFromChapters(projectId: string): Promise<Project> {
    const response = await this.client.post<Project>(
      `/projects/${projectId}/assets/build-from-chapters`,
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

  async updateChapter(projectId: string, chapterNumber: number, data: ChapterUpdate): Promise<Chapter> {
    const response = await this.client.patch<Chapter>(
      `/projects/${projectId}/chapters/${chapterNumber}`,
      data
    )
    return response.data
  }

  async analyzeChapter(projectId: string, chapterNumber: number): Promise<ChapterAnalysisResult> {
    const response = await this.client.post<ChapterAnalysisResult>(
      `/projects/${projectId}/chapters/${chapterNumber}/analyze`,
      {},
      { timeout: this.longTimeout }
    )
    return response.data
  }

  async analyzeAllChapters(projectId: string, force: boolean = false): Promise<ChapterBatchAnalysisResponse> {
    const response = await this.client.post<ChapterBatchAnalysisResponse>(
      `/projects/${projectId}/chapters/analyze-all`,
      {},
      { params: { force }, timeout: this.longTimeout }
    )
    return response.data
  }

  // Character Extraction from Chapters
  async extractCharactersFromChapters(
    projectId: string,
    chapterNumbers: number[],
    autoCreate: boolean = true
  ): Promise<{
    project_id: string
    chapters_scanned: number[]
    new_characters: any[]
    character_evolutions: any[]
    alias_detections: any[]
    suspected_identities: any[]
    characters_created: any[]
  }> {
    const response = await this.client.post(
      `/projects/${projectId}/chapters/extract-characters`,
      {},
      {
        params: { chapter_numbers: chapterNumbers, auto_create: autoCreate },
        paramsSerializer: params => {
          const searchParams = new URLSearchParams()
          for (const key in params) {
            if (Array.isArray(params[key])) {
              params[key].forEach((val: any) => searchParams.append(key, val))
            } else {
              searchParams.append(key, params[key])
            }
          }
          return searchParams.toString()
        },
        timeout: this.longTimeout
      }
    )
    return response.data
  }

  async mergeCharacters(
    projectId: string,
    primaryCharacterId: string,
    secondaryCharacterId: string
  ): Promise<{
    success: boolean
    merged_character: { character_id: string; name: string; aliases: string[] }
    message: string
  }> {
    const response = await this.client.post(
      `/projects/${projectId}/chapters/merge-characters`,
      {},
      {
        params: {
          primary_character_id: primaryCharacterId,
          secondary_character_id: secondaryCharacterId
        }
      }
    )
    return response.data
  }

  async addCharacterAlias(
    projectId: string,
    characterId: string,
    alias: string
  ): Promise<{
    success: boolean
    character_id: string
    name: string
    aliases: string[]
  }> {
    const response = await this.client.post(
      `/projects/${projectId}/chapters/add-character-alias`,
      {},
      { params: { character_id: characterId, alias } }
    )
    return response.data
  }

  // Book
  async getBook(projectId: string): Promise<Book> {
    const response = await this.client.get<Book>(`/projects/${projectId}/book`)
    return response.data
  }

  async updateBook(projectId: string, data: BookUpdate): Promise<Book> {
    const response = await this.client.patch<Book>(`/projects/${projectId}/book`, data)
    return response.data
  }

  async uploadBook(projectId: string, file: File, replaceExisting: boolean = false): Promise<ChapterListResponse> {
    const formData = new FormData()
    formData.append('file', file)
    const response = await this.client.post<ChapterListResponse>(
      `/projects/${projectId}/book/upload`,
      formData,
      {
        headers: { 'Content-Type': 'multipart/form-data' },
        params: { replace_existing: replaceExisting },
        timeout: this.longTimeout
      }
    )
    return response.data
  }

  async analyzeBook(projectId: string): Promise<Book> {
    const response = await this.client.post<Book>(
      `/projects/${projectId}/book/analyze`,
      {},
      { timeout: this.longTimeout }
    )
    return response.data
  }

  // Episodes
  async planEpisodes(projectId: string, data?: EpisodePlanRequest): Promise<Job> {
    const response = await this.client.post<Job>(
      `/projects/${projectId}/episodes/plan`,
      data || {}
    )
    return response.data
  }

  async getPlanResult(projectId: string, jobId: string): Promise<EpisodePlanResponse> {
    const response = await this.client.get<EpisodePlanResponse>(
      `/projects/${projectId}/episodes/plan/${jobId}`
    )
    return response.data
  }

  async createEpisode(projectId: string, data: EpisodeCreate): Promise<Episode> {
    const response = await this.client.post<Episode>(`/projects/${projectId}/episodes`, data)
    return response.data
  }

  async createEpisodesBatch(projectId: string, episodes: EpisodeCreate[]): Promise<EpisodeListResponse> {
    const response = await this.client.post<EpisodeListResponse>(
      `/projects/${projectId}/episodes/batch`,
      { episodes }
    )
    return response.data
  }

  async listEpisodes(projectId: string, status?: string): Promise<EpisodeListResponse> {
    const response = await this.client.get<EpisodeListResponse>(
      `/projects/${projectId}/episodes`,
      { params: status ? { status } : undefined }
    )
    return response.data
  }

  async getEpisode(projectId: string, episodeNumber: number): Promise<Episode> {
    const response = await this.client.get<Episode>(`/projects/${projectId}/episodes/${episodeNumber}`)
    return response.data
  }

  async updateEpisode(projectId: string, episodeNumber: number, data: EpisodeUpdate): Promise<Episode> {
    const response = await this.client.patch<Episode>(
      `/projects/${projectId}/episodes/${episodeNumber}`,
      data
    )
    return response.data
  }

  async deleteEpisode(projectId: string, episodeNumber: number): Promise<void> {
    await this.client.delete(`/projects/${projectId}/episodes/${episodeNumber}`)
  }

  async deleteAllEpisodes(projectId: string): Promise<void> {
    await this.client.delete(`/projects/${projectId}/episodes`)
  }

  async generateEpisodeStoryboard(projectId: string, episodeNumber: number): Promise<ShotListResponse> {
    const response = await this.client.post<ShotListResponse>(
      `/projects/${projectId}/episodes/${episodeNumber}/storyboard/generate`,
      {},
      { timeout: this.longTimeout }
    )
    return response.data
  }

  async startEpisodeRender(projectId: string, episodeNumber: number): Promise<PipelineStartResponse> {
    const response = await this.client.post<PipelineStartResponse>(
      `/projects/${projectId}/episodes/${episodeNumber}/render/start`,
      {},
      { timeout: this.longTimeout }
    )
    return response.data
  }

  async listEpisodeShots(projectId: string, episodeNumber: number): Promise<ShotListResponse> {
    const response = await this.client.get<ShotListResponse>(
      `/projects/${projectId}/episodes/${episodeNumber}/shots`
    )
    return response.data
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

  async generateCharacterReference(
    characterId: string,
    options?: {
      custom_prompt?: string
      style_preset?: string
      negative_prompt?: string
      seed?: number
      num_candidates?: number
      image_provider?: 'google' | 'aliyun'
    }
  ): Promise<GenerateReferenceJobResponse> {
    const response = await this.client.post<GenerateReferenceJobResponse>(
      `/assets/characters/${characterId}/generate-reference`,
      options || {}
    )
    return response.data
  }

  async listCharacterGenerationJobs(
    characterId: string,
    limit: number = 10
  ): Promise<Job[]> {
    const response = await this.client.get<Job[]>(
      `/assets/characters/${characterId}/generation-jobs`,
      { params: { limit } }
    )
    return response.data
  }

  // Character Image Gallery
  async listCharacterImages(
    characterId: string,
    options?: {
      image_type?: string
      training_only?: boolean
    }
  ): Promise<CharacterImageListResponse> {
    const response = await this.client.get<CharacterImageListResponse>(
      `/assets/characters/${characterId}/images`,
      { params: options }
    )
    return response.data
  }

  async getCharacterImage(characterId: string, imageId: string): Promise<CharacterImage> {
    const response = await this.client.get<CharacterImage>(
      `/assets/characters/${characterId}/images/${imageId}`
    )
    return response.data
  }

  async deleteCharacterImage(characterId: string, imageId: string): Promise<void> {
    await this.client.delete(`/assets/characters/${characterId}/images/${imageId}`)
  }

  async uploadCharacterImage(
    characterId: string,
    file: File,
    markForTraining: boolean = true
  ): Promise<CharacterImage> {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('mark_for_training', String(markForTraining))

    const response = await this.client.post<CharacterImage>(
      `/assets/characters/${characterId}/images/upload`,
      formData,
      {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: this.longTimeout,
      }
    )
    return response.data
  }

  async uploadCharacterImagesBatch(
    characterId: string,
    files: File[],
    markForTraining: boolean = true
  ): Promise<CharacterImageListResponse> {
    const formData = new FormData()
    files.forEach(file => formData.append('files', file))
    formData.append('mark_for_training', String(markForTraining))

    const response = await this.client.post<CharacterImageListResponse>(
      `/assets/characters/${characterId}/images/upload-batch`,
      formData,
      {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: this.longTimeout,
      }
    )
    return response.data
  }

  async setAnchorImage(characterId: string, imageId: string): Promise<Character> {
    const response = await this.client.post<Character>(
      `/assets/characters/${characterId}/images/set-anchor`,
      { image_id: imageId }
    )
    return response.data
  }

  async markTrainingImages(
    characterId: string,
    imageIds: string[],
    selected: boolean = true
  ): Promise<CharacterImageListResponse> {
    const response = await this.client.post<CharacterImageListResponse>(
      `/assets/characters/${characterId}/images/mark-training`,
      { image_ids: imageIds, selected }
    )
    return response.data
  }

  async generateCharacterVariants(
    characterId: string,
    options: GenerateVariantRequest
  ): Promise<GenerateReferenceJobResponse> {
    const response = await this.client.post<GenerateReferenceJobResponse>(
      `/assets/characters/${characterId}/images/generate-variants`,
      options
    )
    return response.data
  }

  async batchGenerateCharacterVariants(
    characterId: string,
    options: BatchGenerateVariantRequest
  ): Promise<GenerateReferenceJobResponse> {
    const response = await this.client.post<GenerateReferenceJobResponse>(
      `/assets/characters/${characterId}/images/batch-generate-variants`,
      options
    )
    return response.data
  }

  async getTrainingImages(characterId: string): Promise<CharacterImageListResponse> {
    const response = await this.client.get<CharacterImageListResponse>(
      `/assets/characters/${characterId}/training-images`
    )
    return response.data
  }

  // Voice APIs
  async listAvailableVoices(): Promise<AvailableVoicesResponse> {
    const response = await this.client.get<AvailableVoicesResponse>('/assets/voices')
    return response.data
  }

  async previewVoice(request: VoicePreviewRequest): Promise<VoicePreviewResponse> {
    const response = await this.client.post<VoicePreviewResponse>(
      '/assets/voices/preview',
      request,
      { timeout: 60000 }
    )
    return response.data
  }

  async setCharacterVoice(characterId: string, voiceConfig: VoiceConfig): Promise<Character> {
    const response = await this.client.post<Character>(
      `/assets/characters/${characterId}/voice`,
      voiceConfig
    )
    return response.data
  }

  async uploadCharacterToOSS(characterId: string): Promise<Character> {
    const response = await this.client.post<Character>(
      `/assets/characters/${characterId}/upload-to-oss`
    )
    return response.data
  }

  async batchUploadCharactersToOSS(projectId?: string): Promise<CharacterListResponse> {
    const response = await this.client.post<CharacterListResponse>(
      '/assets/characters/batch-upload-to-oss',
      {},
      { params: projectId ? { project_id: projectId } : undefined }
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

  // LoRA Training
  async startLoRATraining(data: LoRAStartTrainingRequest): Promise<LoRAStartTrainingJobResponse> {
    const response = await this.client.post<LoRAStartTrainingJobResponse>(
      '/lora/train',
      data
    )
    return response.data
  }

  async getLoRA(loraId: string): Promise<CharacterLoRA> {
    const response = await this.client.get<CharacterLoRA>(`/lora/${loraId}`)
    return response.data
  }

  async getLoRAStatus(loraId: string): Promise<LoRATrainingStatusResponse> {
    const response = await this.client.get<LoRATrainingStatusResponse>(`/lora/${loraId}/status`)
    return response.data
  }

  async listCharacterLoRAs(characterId: string): Promise<CharacterLoRA[]> {
    const response = await this.client.get<CharacterLoRA[]>(`/lora/character/${characterId}`)
    return response.data
  }

  async getActiveLoRA(characterId: string): Promise<CharacterLoRA | null> {
    const response = await this.client.get<CharacterLoRA | null>(`/lora/character/${characterId}/active`)
    return response.data
  }

  async cancelLoRATraining(loraId: string): Promise<{ success: boolean; message: string }> {
    const response = await this.client.post<{ success: boolean; message: string }>(`/lora/${loraId}/cancel`)
    return response.data
  }

  // Provider Health Status
  async getProviderStatus(): Promise<ProviderStatusResponse> {
    const response = await this.client.get<ProviderStatusResponse>('/api-test/provider-status')
    return response.data
  }

  // Authentication
  async login(data: LoginRequest): Promise<Token> {
    const response = await this.client.post<Token>('/auth/login', data)
    return response.data
  }

  async register(data: RegisterRequest): Promise<Token> {
    const response = await this.client.post<Token>('/auth/register', data)
    return response.data
  }

  async getCurrentUser(): Promise<User> {
    const response = await this.client.get<User>('/auth/me')
    return response.data
  }

  async refreshToken(): Promise<Token> {
    const response = await this.client.post<Token>('/auth/refresh')
    return response.data
  }

  // Set auth token for subsequent requests
  setAuthToken(token: string | null): void {
    if (token) {
      this.client.defaults.headers.common['Authorization'] = `Bearer ${token}`
    } else {
      delete this.client.defaults.headers.common['Authorization']
    }
  }
}

export const apiClient = new ApiClient()
