import axios from 'axios'
import { ElMessage } from 'element-plus'

// 创建 axios 实例
const api = axios.create({
  baseURL: '/api/v1',
  timeout: 300000,  // 增加到 300 秒（5 分钟），因为知识抽取可能需要较长时间
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器
api.interceptors.request.use(
  config => {
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

// 响应拦截器
api.interceptors.response.use(
  response => {
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
    
    // 判断是否是超时错误
    if (error.code === 'ECONNABORTED' || error.message.includes('timeout')) {
      ElMessage.error('请求超时，处理时间较长，请耐心等待或联系管理员')
    } else {
      const errorMsg = error.response?.data?.detail || error.message || '请求失败'
      ElMessage.error(errorMsg)
    }
    return Promise.reject(error)
  }
)

/**
 * 健康检查接口
 * GET /api/health
 */
export const healthCheck = () => {
  return api.get('/health')
}

/**
 * 上传知识三元组
 * POST /api/v1/fault-tree/upload_knowledge
 * @param {Array} triplets - 三元组数组
 */
export const uploadKnowledge = (triplets) => {
  // 支持两种格式：直接数组或包含 triplets 字段的对象
  const payload = Array.isArray(triplets) ? { triplets } : triplets
  return api.post('/fault-tree/upload_knowledge', payload)
}

/**
 * 上传文件
 * POST /api/v1/document/upload
 * @param {File} file - 上传的文件
 */
export const uploadFile = async (file) => {
  const formData = new FormData()
  formData.append('file', file)

  const response = await api.post('/document/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  })
  return response
}

/**
 * 提取知识
 * POST /api/v1/knowledge/extract
 * @param {Object} data - 提取请求数据
 * @param {string} data.file_id - 文件 ID
 * @param {string} data.mode - 处理模式 (legacy/multimodal)
 * @param {string} data.top_event - 顶事件名称
 */
export const extractKnowledge = (data) => {
  return api.post('/knowledge/extract', data)
}

/**
 * 生成故障树
 * GET /api/v1/fault-tree/generate_tree?top_event=xxx
 * @param {string} topEvent - 顶事件名称
 * @param {boolean} export - 是否导出为文件
 */
export const generateFaultTree = (topEvent, exportToFile = false) => {
  return api.get('/fault-tree/generate_tree', {
    params: {
      top_event: topEvent,
      export: exportToFile
    }
  })
}

/**
 * 下载故障树 JSON 文件
 * @param {string} filename - 文件名
 */
export const downloadFaultTreeFile = (filename) => {
  const baseUrl = import.meta.env.VITE_API_BASE_URL || '/api/v1'
  return `${baseUrl}/fault-tree/download/${filename}`
}

/**
 * 生成并下载故障树（一键操作）
 * @param {string} topEvent - 顶事件名称
 */
export const generateAndDownloadFaultTree = (topEvent) => {
  const baseUrl = import.meta.env.VITE_API_BASE_URL || '/api/v1'
  return `${baseUrl}/fault-tree/generate_and_download?top_event=${encodeURIComponent(topEvent)}`
}

/**
 * 优化故障树（专家修正）
 * POST /api/v1/fault-tree/optimize
 * @param {Object} data - 修正数据
 */
export const optimizeFaultTree = (data) => {
  return api.post('/fault-tree/optimize', data)
}

/**
 * 导出故障树
 * GET /api/v1/fault-tree/export?tree_id=xxx&format=json
 * @param {string} treeId - 树 ID
 * @param {string} format - 导出格式 (json/png/svg)
 */
export const exportFaultTree = (treeId, format = 'json') => {
  return api.get('/fault-tree/export', {
   params: { tree_id: treeId, format }
  })
}

/**
 * AI 对话接口
 * POST /api/v1/ai/chat
 * @param {Object} data - 对话请求数据
 * @param {Array} data.messages - 消息历史
 * @param {Object} data.context - 故障树上下文
 */
export const chatWithAI = (data) => {
  return api.post('/ai/chat', data)
}

export default api
