export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
}

export interface PipelineStartResponse {
  job_id: string
  project_id: string
  message: string
}

export interface UserInfo {
  username: string
  disabled: boolean
  scopes: string[]
}

export interface AuthBootstrap {
  auth_disabled: boolean
  allow_registration: boolean
  has_users: boolean
}

export interface ActionLink {
  label: string
  target: string
}

export interface OperationSummary {
  id: string
  type: string
  label: string
  status: string
  progress: number
  created_at: string
  completed_at?: string | null
  error_message?: string | null
}

export interface StageSummary {
  key: string
  label: string
  status: string
  progress: number
  metrics: Record<string, unknown>
  blockers: string[]
  primary_action?: ActionLink | null
}

export interface ProjectHeaderSummary {
  id: string
  name: string
  description?: string | null
  style_preset?: string | null
  status: string
  current_stage: string
  current_stage_label: string
  completion_rate: number
  updated_at: string
  next_action?: ActionLink | null
}

export interface ProjectCardSummary extends ProjectHeaderSummary {
  blockers: string[]
  metrics: Record<string, unknown>
}

export interface ProjectCardListResponse {
  items: ProjectCardSummary[]
  total: number
}

export interface DashboardResponse {
  project: ProjectHeaderSummary
  metrics: Record<string, unknown>
  stage_summaries: StageSummary[]
  blockers: string[]
  recent_operations: OperationSummary[]
}

export interface BookWorkspaceItem {
  id?: string | null
  title?: string | null
  author?: string | null
  genre?: string | null
  source_type: string
  upload_status: string
  total_chapters: number
  uploaded_chapters: number
  total_words: number
  ai_summary?: string | null
  suggested_episodes?: number | null
}

export interface ChapterWorkspaceItem {
  chapter_id: string
  chapter_number: number
  title?: string | null
  word_count: number
  status: string
  emotional_arc?: string | null
  importance_score: number
  key_events: string[]
  characters_appeared: string[]
  suggested_episode?: number | null
}

export interface CharacterWorkspaceItem {
  character_id: string
  name: string
  aliases: string[]
  bio: string
  appearance_prompt: string
  first_appearance_chapter: number
  voice_id?: string | null
  anchor_image_url?: string | null
  reference_image_url?: string | null
  asset_status: string
  review_status: string
  source_chapters: number[]
  image_counts: Record<string, number>
  issues: string[]
}

export interface EpisodePlanSuggestionSummary {
  episode_number: number
  title: string
  start_chapter: number
  end_chapter: number
  synopsis: string
  estimated_duration_minutes: number
}

export interface EpisodePlanDraftSummary {
  job_id: string
  status: string
  updated_at: string
  reasoning?: string | null
  total_estimated_duration?: number | null
  suggestions: EpisodePlanSuggestionSummary[]
}

export interface EpisodeWorkspaceItem {
  id: string
  episode_number: number
  title?: string | null
  synopsis?: string | null
  start_chapter: number
  end_chapter: number
  target_duration_minutes: number
  actual_duration_minutes?: number | null
  status: string
  shot_count: number
  has_delivery: boolean
  output_video_url?: string | null
  updated_at: string
}

export interface DeliveryAssetSummary {
  episode_id: string
  episode_number: number
  title?: string | null
  version_label: string
  duration_minutes?: number | null
  video_url?: string | null
  updated_at: string
}

export interface WorkspaceResponse extends DashboardResponse {
  active_operations: OperationSummary[]
  book?: BookWorkspaceItem | null
  chapters: ChapterWorkspaceItem[]
  characters: CharacterWorkspaceItem[]
  episode_plan_draft?: EpisodePlanDraftSummary | null
  episodes: EpisodeWorkspaceItem[]
  deliveries: DeliveryAssetSummary[]
}

export interface ProjectCreateRequest {
  name: string
  description?: string
  style_preset?: string
}

export interface CharacterImage {
  id: string
  character_id: string
  image_type: string
  image_path?: string | null
  image_url?: string | null
  thumbnail_url?: string | null
  prompt?: string | null
  pose?: string | null
  expression?: string | null
  angle?: string | null
  style_preset?: string | null
  is_selected_for_training: boolean
  is_anchor: boolean
  quality_score?: number | null
  created_at: string
}

export interface CharacterImageListResponse {
  items: CharacterImage[]
  total: number
}

export interface VoiceOption {
  id: string
  name: string
  gender?: string
  description?: string
}

export interface AvailableVoicesResponse {
  provider: string
  voices: VoiceOption[]
}

export interface VoicePreviewResponse {
  audio_url: string
  duration: number
  voice_id: string
  text: string
}

export interface JobResponse {
  id: string
  project_id: string
  job_type: string
  celery_task_id?: string | null
  status: string
  progress: number
  result?: Record<string, unknown> | null
  error_message?: string | null
  created_at: string
  started_at?: string | null
  completed_at?: string | null
}

export interface JobListResponse {
  items: JobResponse[]
  total: number
}

export interface ShotItem {
  shot_id: number
  project_id?: string | null
  duration: number
  scene_description: string
  visual_prompt: string
  camera_movement: string
  characters_in_shot: string[]
  dialogue?: string | null
  action_type?: string | null
  sequence_order: number
  created_at: string
}

export interface ShotListResponse {
  items: ShotItem[]
  total: number
}

export interface EpisodePlanResult {
  suggested_episodes: EpisodePlanSuggestionSummary[]
  total_estimated_duration: number
  reasoning: string
}
