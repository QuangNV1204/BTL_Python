import { getSession } from '../../../shared/auth/session'
import type { GeneratedCards, GeneratedQuiz, GenerationRequest, QuizQuestion } from './api'

export type AiDraft =
  | {
    kind: 'quiz'
    generation_id: string
    source_truncated: boolean
    items: QuizQuestion[]
    quiz_id?: string
    saved_count: number
    request?: GenerationRequest
    title?: string
  }
  | {
    kind: 'flashcard'
    generation_id: string
    source_truncated: boolean
    items: { front_text: string; back_text: string }[]
    saved_count: number
    request?: GenerationRequest
  }

const key = (lessonId: string) => `lesson-ai-preview:${getSession().user?.id ?? 'guest'}:${lessonId}`

export function readDraft(lessonId: string): AiDraft | null {
  try {
    return JSON.parse(sessionStorage.getItem(key(lessonId)) ?? 'null') as AiDraft | null
  } catch {
    return null
  }
}

export function writeDraft(lessonId: string, draft: AiDraft): void {
  try {
    sessionStorage.setItem(key(lessonId), JSON.stringify(draft))
  } catch {
  }
}

export function clearDraft(lessonId: string): void {
  try {
    sessionStorage.removeItem(key(lessonId))
  } catch {
  }
}

export function quizDraft(result: GeneratedQuiz): AiDraft {
  return {
    kind: 'quiz',
    generation_id: result.generation_id,
    source_truncated: result.source_truncated,
    items: result.candidate.questions,
    saved_count: 0,
  }
}

export function cardsDraft(result: GeneratedCards): AiDraft {
  return {
    kind: 'flashcard',
    generation_id: result.generation_id,
    source_truncated: result.source_truncated,
    items: result.candidate.flashcards,
    saved_count: 0,
  }
}
