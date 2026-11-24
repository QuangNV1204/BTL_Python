import { isApiError } from '../../../shared/api/client'
import { saveDraftSnapshot } from './quiz.api'
import type { QuestionWriteRequest, QuizQuestionAuthor } from './quiz.types'

export function questionPayload(question: QuizQuestionAuthor, index: number): QuestionWriteRequest {
  return {
    content: question.content.trim(),
    explanation: question.explanation?.trim() || null,
    order_index: index,
    options: question.options.map((option, position) => ({
      content: option.content.trim(), is_correct: option.isCorrect, order_index: position,
    })),
  }
}

export function createDraftSaver() {
  let pending: { quizId: string; body: Parameters<typeof saveDraftSnapshot>[1] } | undefined
  return async (quizId: string, title: string, questions: QuizQuestionAuthor[]) => {
    if (!pending) {
      pending = { quizId, body: {
        request_id: crypto.randomUUID(), title: title.trim(),
        questions: questions.map((q, i) => ({ ...questionPayload(q, i), ...(q.id ? { id: q.id } : {}) })),
      } }
    }
    try {
      const saved = await saveDraftSnapshot(pending.quizId, pending.body)
      pending = undefined
      return saved
    } catch (error) {
      if (isApiError(error) && error.status >= 400 && error.status < 500) pending = undefined
      throw error
    }
  }
}
