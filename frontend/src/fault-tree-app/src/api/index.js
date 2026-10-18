import axios from 'axios'
import { ElMessage } from 'element-plus'

const WORKSPACE_STORAGE_KEY = 'LIGHTRAG-WORKSPACE'

const getCurrentWorkspaceId = () => {
  if (typeof window === 'undefined') return null
  const workspaceId = window.localStorage.getItem(WORKSPACE_STORAGE_KEY)
  return typeof workspaceId === 'string' && workspaceId.trim() ? workspaceId.trim() : null
}

const setCurrentWorkspaceId = (workspaceId) => {
  if (typeof window === 'undefined') return
  const normalized = typeof workspaceId === 'string' ? workspaceId.trim() : ''
  if (normalized) {
    window.localStorage.setItem(WORKSPACE_STORAGE_KEY, normalized)
    return
  }
  window.localStorage.removeItem(WORKSPACE_STORAGE_KEY)
}

const clearCurrentWorkspaceId = () => {
  setCurrentWorkspaceId(null)
}

const emitApiError = (message) => {
  console.error('[fault-tree-ui]', message)
  if (typeof window !== 'undefined') {
    window.dispatchEvent(
      new CustomEvent('fault-tree-api-error', {
        detail: { message }
      })
    )
  }
}

const api = axios.create({
  baseURL: '',
  timeout: 300000,
  headers: {
    'Content-Type': 'application/json'
  }
})

api.interceptors.request.use(
  config => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('LIGHTRAG-API-TOKEN') : null
    if (token) {
      config.headers = config.headers ?? {}
      config.headers.Authorization = `Bearer ${token}`
    }
    const workspaceId = getCurrentWorkspaceId()
    if (workspaceId) {
      config.headers = config.headers ?? {}
      config.headers['LIGHTRAG-WORKSPACE'] = workspaceId
    }
    console.log('📤 发起请求:', {
      url: config.url,
      method: config.method,
      baseURL: config.baseURL,
      timeout: config.timeout,
      data: config.data ? JSON.stringify(config.data).substring(0, 200) + '...' : undefined
    })
    return config
  },
  error => {
    console.error('❌ 请求错误:', error)
    return Promise.reject(error)
  }
)

api.interceptors.response.use(
  response => {
    if (response?.data?.workspace_id) {
      setCurrentWorkspaceId(response.data.workspace_id)
    }
    console.log('✅ 响应成功:', {
      url: response.config.url,
      method: response.config.method,
      status: response.status,
      dataSize: JSON.stringify(response.data).length
    })
    return response.data
  },
  error => {
    console.error('❌ 响应失败:', {
      url: error.config?.url,
      method: error.config?.method,
      errorType: error.code || error.name,
      errorMessage: error.message,
      responseData: error.response?.data
    })
    
    if (error.code === 'ECONNABORTED' || error.message.includes('timeout')) {
      emitApiError('请求超时，处理时间较长，请耐心等待或联系管理员')
      ElMessage.error('请求超时，处理时间较长，请耐心等待或联系管理员')
    } else {
      const errorMsg = error.response?.data?.detail || error.message || '请求失败'
      emitApiError(errorMsg)
      ElMessage.error(errorMsg)
    }
    return Promise.reject(error)
  }
)

export const healthCheck = () => {
  return api.get('/health')
}

export const uploadKnowledge = (triplets) => {
  const payload = Array.isArray(triplets) ? { triplets } : triplets
  return api.post('/fault-tree/upload_knowledge', payload)
}

export const uploadFile = async (file) => {
  clearCurrentWorkspaceId()

  const formData = new FormData()
  formData.append('file', file)

  const response = await api.post('/documents/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  })
  return response
}

export const extractKnowledge = (data) => {
  return api.post('/knowledge/extract', data)
}

export const generateFaultTree = (topEvent, exportToFile = false) => {
  return api.get('/graph/fault-tree/export', {
    params: {
      top_event: topEvent,
      export: exportToFile
    }
  })
}

export const downloadFaultTreeFile = (filename) => {
  const baseUrl = import.meta.env.VITE_API_BASE_URL || ''
  return `${baseUrl}/fault-tree/download/${filename}`
}

export const generateAndDownloadFaultTree = (topEvent) => {
  const baseUrl = import.meta.env.VITE_API_BASE_URL || ''
  return `${baseUrl}/fault-tree/generate_and_download?top_event=${encodeURIComponent(topEvent)}`
}

export const optimizeFaultTree = (data) => {
  return api.post('/fault-tree/optimize', data)
}

export const validateFaultTree = (data) => {
  return api.post('/fault-tree/validate', data)
}

export const exportFaultTree = (treeId, format = 'json') => {
  return api.get('/fault-tree/export', {
    params: { tree_id: treeId, format }
  })
}

export const chatWithAI = (data) => {
  return api.post('/ai/chat', data)
}

export default api