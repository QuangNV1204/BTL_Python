import { addQuestion, deleteQuestion, getQuiz, updateQuestion, updateQuiz } from './quiz.api'
import type { QuestionWriteRequest, QuizQuestionAuthor } from './quiz.types'

export function questionPayload(question: QuizQuestionAuthor, index: number): QuestionWriteRequest {
  return {
    content: question.content.trim(),
    explanation: question.explanation?.trim() || undefined,
    order_index: index,
    options: question.options.map((option, position) => ({
      content: option.content.trim(), is_correct: option.isCorrect, order_index: position,
    })),
  }
}

// The existing API is per-question, not atomic. Park occupied positions first.
// Reconcile IDs after every acknowledged write so subsequent saves never recreate them.
export async function saveQuizDraft(quizId: string, title: string, questions: QuizQuestionAuthor[],
  deletedIds: string[], acknowledged: (index: number, saved: QuizQuestionAuthor) => void,
  deleted: (id: string) => void): Promise<void> {
  const current = await getQuiz(quizId)
  if (current.status !== 'DRAFT') throw new Error('Quiz không còn là bản nháp. Hãy tải lại trang.')
  if (current.title !== title.trim()) await updateQuiz(quizId, { title: title.trim() })
  for (const id of deletedIds) {
    if (current.questions.some((question) => question.id === id)) await deleteQuestion(id)
    deleted(id)
  }
  const existing = current.questions.filter((question) => !deletedIds.includes(question.id!))
  const base = Math.max(questions.length, ...current.questions.map((question) => question.orderIndex)) + 1
  if (base + existing.length > 2147483647) throw new Error('Thứ tự câu hỏi vượt giới hạn. Hãy tải lại trang.')
  for (let index = 0; index < existing.length; index++) {
    await updateQuestion(existing[index].id!, questionPayload(existing[index], base + index))
  }
  for (let index = 0; index < questions.length; index++) {
    const question = questions[index]
    const payload = questionPayload(question, index)
    const saved = question.id
      ? await updateQuestion(question.id, payload)
      : await addQuestion(quizId, payload)
    acknowledged(index, saved)
  }
}
