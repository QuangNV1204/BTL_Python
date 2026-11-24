
export type Id = string

export type IsoDateTime = string

export interface Page<T> {
  items: T[]
  page: number
  page_size: number
  total: number
}

export interface PageParams {
  page?: number
  page_size?: number
  sort?: string
}

export type ErrorCode =
  | 'VALIDATION_ERROR'
  | 'UNAUTHENTICATED'
  | 'FORBIDDEN'
  | 'NOT_FOUND'
  | 'EMAIL_ALREADY_EXISTS'
  | 'EMAIL_NOT_VERIFIED'
  | 'INVALID_EMAIL_VERIFICATION_TOKEN'
  | 'INVALID_PASSWORD_RESET_TOKEN'
  | 'EMAIL_SEND_FAILED'
  | 'ACCOUNT_INACTIVE'
  | 'INVALID_STATE'
  | 'COURSE_NOT_FREE'
  | 'ENROLLMENT_REQUIRED'
  | 'INVALID_QUIZ'
  | 'INVALID_ANSWER'
  | 'FILE_TOO_LARGE'
  | 'UNSUPPORTED_FILE_TYPE'
  | 'SOURCE_TEXT_EMPTY'
  | 'AI_OUTPUT_INVALID'
  | 'AI_PROVIDER_ERROR'
  | 'AI_TIMEOUT'
  | 'RATE_LIMITED'
  | 'RESOURCE_IN_USE'
  | 'NETWORK_ERROR'
  | (string & {})

export interface FieldErrorDetail {
  field: string
  message: string
}

export interface ApiErrorBody {
  code: ErrorCode
  message: string
  details?: FieldErrorDetail[]
  request_id?: string
}

export type Role = 'ADMIN' | 'TEACHER' | 'STUDENT'
