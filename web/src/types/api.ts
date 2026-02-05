// Enums
export enum ProjectStatus {
  DRAFT = 'DRAFT',
  ASSETS_READY = 'ASSETS_READY',
  STORYBOARD_READY = 'STORYBOARD_READY',
  RENDERING = 'RENDERING',
  COMPOSITED = 'COMPOSITED',
  DONE = 'DONE',
  FAILED = 'FAILED'
}

export enum JobStatus {
  PENDING = 'PENDING',
  STARTED = 'STARTED',
  SUCCESS = 'SUCCESS',
  FAILURE = 'FAILURE',
  REVOKED = 'REVOKED'
}

export enum JobType {
  ASSET_GENERATION = 'ASSET_GENERATION',
  STORYBOARD_GENERATION = 'STORYBOARD_GENERATION',
  SHOT_RENDER = 'SHOT_RENDER',
  VIDEO_COMPOSITION = 'VIDEO_COMPOSITION',
  FULL_PIPELINE = 'FULL_PIPELINE'
}

export enum ShotRenderStatus {
  PENDING = 'PENDING',
  GENERATING_IMAGE = 'GENERATING_IMAGE',
  GENERATING_VIDEO = 'GENERATING_VIDEO',
  GENERATING_AUDIO = 'GENERATING_AUDIO',
  COMPOSITING = 'COMPOSITING',
  SUCCESS = 'SUCCESS',
  FAILURE = 'FAILURE'
}

export enum ChapterStatus {
  PENDING = 'PENDING',
  EXTRACTING = 'EXTRACTING',
  READY = 'READY',
  FAILED = 'FAILED'
}

// Metadata types - use specific interfaces instead of Record<string, any>
export interface ProjectMetadata {
  genre?: string
  target_audience?: string
  estimated_duration?: number
  tags?: string[]
  [key: string]: unknown
}

export interface CharacterMetadata {
  age?: number
  personality?: string
  background?: string
  relationships?: Record<string, string>
  [key: string]: unknown
}

export interface RenderSettings {
  resolution?: string
  fps?: number
  quality?: string
  [key: string]: unknown
}

export interface JobResult {
  output_path?: string
  duration?: number
  frames_rendered?: number
  [key: string]: unknown
}

// Project Types
export interface ProjectCreate {
  name: string
  description?: string
  script_content?: string
  style_preset?: string
  project_metadata?: ProjectMetadata
}

export interface ProjectUpdate {
  name?: string
  description?: string
  script_content?: string
  style_preset?: string
  status?: ProjectStatus
  project_metadata?: ProjectMetadata
}

export interface Project {
  id: string
  name: string
  description?: string
  status: ProjectStatus
  script_content?: string
  style_preset?: string
  output_video_path?: string
  output_video_url?: string  // OSS URL，用于播放/下载
  error_message?: string
  project_metadata?: ProjectMetadata
  created_at: string
  updated_at: string
}

export interface ProjectListResponse {
  items: Project[]
  total: number
  page: number
  page_size: number
}

export interface ProjectStatusUpdate {
  status: ProjectStatus
  error_message?: string
}

// Character Types
export interface CharacterCreate {
  character_id: string
  name: string
  prompt_base: string
  reference_image_path: string
  voice_id?: string
  character_metadata?: CharacterMetadata
}

export interface CharacterUpdate {
  name?: string
  prompt_base?: string
  reference_image_path?: string
  voice_id?: string
  character_metadata?: CharacterMetadata
}

export interface Character {
  character_id: string
  project_id: string
  name: string
  prompt_base?: string
  reference_image_path?: string
  voice_id?: string
  character_metadata?: CharacterMetadata
  created_at: string
}

export interface CharacterListResponse {
  items: Character[]
  total: number
}

// Shot Types
export interface ShotCreate {
  shot_id: string
  duration: number
  scene_description: string
  visual_prompt?: string
  camera_movement?: string
  characters_in_shot?: string[]
  dialogue?: string
  action_type?: string
  sequence_order: number
}

export interface Shot {
  shot_id: string
  project_id: string
  duration: number
  scene_description: string
  visual_prompt?: string
  camera_movement?: string
  characters_in_shot?: string[]
  dialogue?: string
  action_type?: string
  sequence_order: number
  created_at: string
}

export interface ShotListResponse {
  items: Shot[]
  total: number
}

// Job Types
export interface JobCreate {
  project_id: string
  job_type: JobType
}

export interface Job {
  id: string
  project_id: string
  job_type: JobType
  celery_task_id?: string
  status: JobStatus
  progress: number
  result?: JobResult
  error_message?: string
  error_traceback?: string
  created_at: string
  started_at?: string
  completed_at?: string
}

export interface JobListResponse {
  items: Job[]
  total: number
}

export interface JobProgressUpdate {
  progress: number
  status?: JobStatus
}

export interface JobStatusUpdate {
  status: JobStatus
  error_message?: string
  error_traceback?: string
  result?: JobResult
}

// Shot Render Types
export interface ShotRender {
  id: string
  project_id: string
  shot_id: string
  job_id: string
  status: ShotRenderStatus
  progress: number
  image_path?: string
  video_path?: string
  audio_path?: string
  composited_path?: string
  render_settings?: RenderSettings
  error_message?: string
  created_at: string
  updated_at: string
}

export interface ShotRenderListResponse {
  items: ShotRender[]
  total: number
}

// Chapter Types
export interface ChapterCreate {
  chapter_number: number
  title: string
  content: string
}

export interface Chapter {
  chapter_id: string
  project_id: string
  chapter_number: number
  title: string
  content: string
  status: ChapterStatus
  created_at: string
  updated_at: string
}

export interface ChapterListResponse {
  items: Chapter[]
  total: number
}

// Pipeline Types
export interface PipelineStartRequest {
  project_id: string
  skip_asset_generation?: boolean
  parallel_renders?: number
}

export interface PipelineStartResponse {
  job_id: string
  project_id: string
  message: string
}

// Error Types
export interface ErrorDetail {
  loc: string[]
  msg: string
  type: string
}

export interface ErrorResponse {
  error: string
  message: string
  details?: Record<string, unknown>
}

export interface ValidationErrorResponse {
  error: string
  message: string
  details?: ErrorDetail[]
}

// Status helper sets for business logic
export const PROCESSING_STATUSES: readonly ProjectStatus[] = [
  ProjectStatus.RENDERING,
  ProjectStatus.COMPOSITED
] as const

export const PIPELINE_READY_STATUSES: readonly ProjectStatus[] = [
  ProjectStatus.DRAFT,
  ProjectStatus.ASSETS_READY,
  ProjectStatus.STORYBOARD_READY,
  ProjectStatus.FAILED
] as const

export const ASSET_BUILD_STATUSES: readonly ProjectStatus[] = [
  ProjectStatus.DRAFT
] as const

export const STORYBOARD_READY_STATUSES: readonly ProjectStatus[] = [
  ProjectStatus.DRAFT,
  ProjectStatus.ASSETS_READY
] as const

export const ACTIVE_JOB_STATUSES: readonly JobStatus[] = [
  JobStatus.PENDING,
  JobStatus.STARTED
] as const

// API Test Types
export interface ProviderTestResult {
  provider: string
  category: string
  status: 'success' | 'failed' | 'skipped'
  message: string
  latency_ms?: number
  details?: Record<string, unknown>
}

export interface AllTestsResponse {
  timestamp: string
  results: ProviderTestResult[]
  summary: {
    total: number
    success: number
    failed: number
    skipped: number
  }
}

export interface ProviderConfig {
  configured: boolean
  key?: string
  model?: string
  endpoint?: string
  access_key?: string
  region?: string
  app_id?: string
  group_id?: string
}

export interface ConfigStatusResponse {
  providers: {
    llm: {
      google: ProviderConfig
      openai: ProviderConfig
      deepseek: ProviderConfig
      doubao: ProviderConfig
      current_provider: string
    }
    image: {
      google: ProviderConfig
      aliyun: ProviderConfig
      replicate: ProviderConfig
      current_provider: string
    }
    video: {
      google: ProviderConfig
      aliyun: ProviderConfig
      replicate: ProviderConfig
      volcengine: ProviderConfig
      current_provider: string
    }
    tts: {
      openai: ProviderConfig
      doubao: ProviderConfig
      aliyun: ProviderConfig
      minimax: ProviderConfig
      zhipu: ProviderConfig
      current_provider: string
    }
    vlm: {
      backend: string
      model: string
      configured: boolean
    }
  }
}
