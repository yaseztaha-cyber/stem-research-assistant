import axios from 'axios'

declare global {
  interface Window {
    electronAPI?: {
      getBackendUrl: () => Promise<string>
    }
  }
}

async function getBaseUrl(): Promise<string> {
  if (window.electronAPI) {
    try {
      return await window.electronAPI.getBackendUrl()
    } catch {}
  }
  // Desktop app: pywebview serves frontend on 8766, backend on 8765
  if (window.location.port === '8766') {
    return 'http://127.0.0.1:8765'
  }
  return import.meta.env.VITE_API_URL || 'http://localhost:8001'
}

export const api = axios.create({
  timeout: 30000,
})

api.interceptors.request.use(async (config) => {
  config.baseURL = await getBaseUrl()
  return config
})

export interface Document {
  id: string
  filename: string
  original_filename: string
  file_type: string
  file_size: number
  status: string
  page_count: number
  source_quality: string
  created_at: string
}

export const uploadDocument = (file: File) => {
  const fd = new FormData()
  fd.append('file', file)
  return api.post<Document>('/api/documents/upload', fd)
}
export const listDocuments = () => api.get<Document[]>('/api/documents').then(r=>r.data)
export const listChunks = (id: string) => api.get(`/api/documents/${id}/chunks`).then(r=>r.data)
export const ragQuery = (payload: any) => api.post('/api/rag/query', payload).then(r=>r.data)
export const explain = (payload: any) => api.post('/api/rag/explain', payload).then(r=>r.data)
export const getEquations = (documentId?: string) => api.get('/api/learning/equations', {params: {document_id: documentId}}).then(r=>r.data)
export const explainEquation = (id: string) => api.get(`/api/learning/equations/${id}/explain`).then(r=>r.data)
export const flashcards = (documentId?: string) => api.post('/api/learning/flashcards', null, {params: {document_id: documentId, limit: 8}}).then(r=>r.data)
export const listFlashcards = (documentId?: string) => api.get('/api/learning/flashcards', {params: {document_id: documentId}}).then(r=>r.data)
export const problems = (documentId?: string, difficulty='medium') => api.post('/api/learning/problems', null, {params: {document_id: documentId, difficulty, limit: 5}}).then(r=>r.data)
export const questions = (documentId?: string) => api.post('/api/learning/questions', null, {params: {document_id: documentId, limit: 8}}).then(r=>r.data)
export const listCollections = () => api.get('/api/collections').then(r=>r.data)
export const createCollection = (name: string, description?: string) => api.post('/api/collections', {name, description}).then(r=>r.data)
export const addToCollection = (cid: string, did: string) => api.post(`/api/collections/${cid}/documents/${did}`).then(r=>r.data)
export const search = (q: string) => api.get('/api/search', {params: {q}}).then(r=>r.data)
export const citation = (docId: string, style='apa') => api.get(`/api/learning/citations/${docId}`, {params: {style}}).then(r=>r.data)
export const analyzePaper = (id: string) => api.get(`/api/analysis/paper/${id}`).then(r=>r.data)
export const analyzeLab = (id: string) => api.get(`/api/analysis/lab/${id}`).then(r=>r.data)
export const analyzeDataset = (id: string) => api.post(`/api/documents/${id}/analyze-dataset`).then(r=>r.data)
export const evaluation = () => api.get('/api/evaluation/run').then(r=>r.data)
export const benchmark = () => api.get('/api/evaluation/benchmark').then(r=>r.data)
export const errorAnalysis = () => api.get('/api/evaluation/error-analysis').then(r=>r.data)
export const queryClassify = (q: string) => api.get('/api/rag/query-classify', {params: {q}}).then(r=>r.data)
export const retrievalTrace = (q: string, docId?: string) => api.get('/api/rag/trace', {params: {query: q, document_id: docId}}).then(r=>r.data)
export const validateEquation = (eq: string) => api.get('/api/rag/validate-equation', {params: {equation: eq}}).then(r=>r.data)
export const gradingCases = (includeAnswers = false) => api.get('/api/grading/cases', {params: {include_answers: includeAnswers}}).then(r=>r.data)
export const submitGrade = (payload: any) => api.post('/api/grading/grade', payload).then(r=>r.data)
export const gradingConsensus = (caseId?: string) => api.get('/api/grading/consensus', {params: caseId ? {case_id: caseId} : {}}).then(r=>r.data)
export const gradingCorrelation = () => api.get('/api/grading/correlation').then(r=>r.data)
export const goldSet = () => api.get('/api/grading/gold-set').then(r=>r.data)
export const retrievalVsAnswer = () => api.get('/api/grading/retrieval-vs-answer').then(r=>r.data)
export const gradingProgress = () => api.get('/api/grading/progress').then(r=>r.data)
export const makePair = (caseId: string, seed = 7) => api.post('/api/grading/pair', { evaluation_case_id: caseId, seed }).then(r=>r.data)
export const submitPairwiseBlind = (payload: any) => api.post('/api/grading/pairwise-blind', payload).then(r=>r.data)
export const pairwiseSummary = () => api.get('/api/grading/pairwise/summary').then(r=>r.data)
export const preflight = () => api.get('/api/evaluation/preflight').then(r=>r.data)
export const benchmarkMatrix = (strict = false) => api.get('/api/evaluation/benchmark', {params: {strict}}).then(r=>r.data)
export const health = () => api.get('/api/health').then(r=>r.data)
