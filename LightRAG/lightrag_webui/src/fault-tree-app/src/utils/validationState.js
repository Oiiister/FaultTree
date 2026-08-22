const SEVERITY_WEIGHT = {
  warning: 1,
  error: 2
}

export const getValidationCategoryText = (category) => {
  if (category === 'structure_integrity') return '结构完整性'
  if (category === 'hierarchy_reasonableness') return '层级合理性'
  if (category === 'knowledge_graph_consistency') return '知识图谱一致性'
  return '逻辑关系规范性'
}

export const buildValidationPayload = (nodes, edges) => ({
  nodes: (nodes || []).map((node) => {
    const payload = {
      id: node.id,
      label: String(node.label || (node.type === 'gate' ? `${node.gate || 'AND'}门` : `节点-${node.id}`)).trim(),
      type: node.type
    }
    if (node.entity_reference) {
      payload.entity_reference = String(node.entity_reference).trim()
    }
    if (node.type === 'gate') {
      payload.gate = node.gate || 'AND'
    }
    return payload
  }),
  edges: (edges || []).map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target
  }))
})

export const buildTwoPhaseValidationRequests = (nodes, edges) => {
  const payload = buildValidationPayload(nodes, edges)

  return {
    ruleRequest: {
      ...payload,
      enable_llm_suggestions: false,
      enable_kg_validation: false
    },
    enhancedRequest: {
      ...payload,
      enable_llm_suggestions: true,
      enable_kg_validation: true
    }
  }
}

export const buildIssueSeverityMap = (issues, key) => {
  const map = {}

  for (const issue of issues || []) {
    const severity = issue?.severity
    const ids = issue?.[key] || []
    for (const id of ids) {
      if (!id) continue
      if (!map[id] || SEVERITY_WEIGHT[severity] > SEVERITY_WEIGHT[map[id]]) {
        map[id] = severity
      }
    }
  }

  return map
}

export const findFirstValidationFocusTarget = (issue, nodes, edges) => {
  const nodeIdSet = new Set((nodes || []).map((node) => node.id))
  const edgeIdSet = new Set((edges || []).map((edge) => edge.id))

  for (const nodeId of issue?.node_ids || []) {
    if (nodeIdSet.has(nodeId)) {
      return { type: 'node', id: nodeId }
    }
  }

  for (const edgeId of issue?.edge_ids || []) {
    if (edgeIdSet.has(edgeId)) {
      return { type: 'edge', id: edgeId }
    }
  }

  return null
}

export const withTemporarilyHiddenValidationFindings = async ({ getVisible, setVisible, sync, task }) => {
  const previousVisible = Boolean(getVisible())

  if (previousVisible) {
    setVisible(false)
    if (sync) {
      await sync()
    }
  }

  try {
    return await task()
  } finally {
    if (Boolean(getVisible()) !== previousVisible) {
      setVisible(previousVisible)
      if (sync) {
        await sync()
      }
    }
  }
}