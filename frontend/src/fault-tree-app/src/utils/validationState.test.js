import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildIssueSeverityMap,
  buildValidationPayload,
  buildTwoPhaseValidationRequests,
  findFirstValidationFocusTarget,
  getValidationCategoryText,
  withTemporarilyHiddenValidationFindings
} from './validationState.js'

test('buildValidationPayload normalizes nodes and edges for the backend contract', () => {
  const payload = buildValidationPayload(
    [
      { id: 'top_1', label: '主泵失效', type: 'top', entity_reference: 'kg://top-event/main-pump' },
      { id: 'gate_1', label: '', type: 'gate', gate: 'OR' },
      { id: 'basic_1', type: 'basic' }
    ],
    [{ id: 'edge_1', source: 'top_1', target: 'gate_1', style: { color: '#fff' } }]
  )

  assert.deepEqual(payload, {
    nodes: [
      { id: 'top_1', label: '主泵失效', type: 'top', entity_reference: 'kg://top-event/main-pump' },
      { id: 'gate_1', label: 'OR门', type: 'gate', gate: 'OR' },
      { id: 'basic_1', label: '节点-basic_1', type: 'basic' }
    ],
    edges: [{ id: 'edge_1', source: 'top_1', target: 'gate_1' }]
  })
})

test('buildTwoPhaseValidationRequests keeps entity references in the KG enhancement request', () => {
  const { ruleRequest, enhancedRequest } = buildTwoPhaseValidationRequests(
    [
      { id: 'top_1', label: '主泵失效', type: 'top', entity_reference: 'kg://top-event/main-pump' },
      { id: 'basic_1', label: '线路短路', type: 'basic', entity_reference: 'kg://event/short-circuit' }
    ],
    [{ id: 'edge_1', source: 'basic_1', target: 'top_1' }]
  )

  assert.equal(ruleRequest.enable_llm_suggestions, false)
  assert.equal(ruleRequest.enable_kg_validation, false)
  assert.equal(enhancedRequest.enable_llm_suggestions, true)
  assert.equal(enhancedRequest.enable_kg_validation, true)
  assert.deepEqual(enhancedRequest.nodes, [
    { id: 'top_1', label: '主泵失效', type: 'top', entity_reference: 'kg://top-event/main-pump' },
    { id: 'basic_1', label: '线路短路', type: 'basic', entity_reference: 'kg://event/short-circuit' }
  ])
  assert.deepEqual(enhancedRequest.edges, [{ id: 'edge_1', source: 'basic_1', target: 'top_1' }])
})

test('buildIssueSeverityMap keeps the highest severity per target id', () => {
  const issues = [
    { severity: 'warning', node_ids: ['node_1', 'node_2'] },
    { severity: 'error', node_ids: ['node_2'], edge_ids: ['edge_1'] },
    { severity: 'warning', edge_ids: ['edge_1', 'edge_2'] }
  ]

  assert.deepEqual(buildIssueSeverityMap(issues, 'node_ids'), {
    node_1: 'warning',
    node_2: 'error'
  })
  assert.deepEqual(buildIssueSeverityMap(issues, 'edge_ids'), {
    edge_1: 'error',
    edge_2: 'warning'
  })
})

test('findFirstValidationFocusTarget prefers valid node ids and falls back to edges', () => {
  const nodes = [{ id: 'node_1' }]
  const edges = [{ id: 'edge_1' }]

  assert.deepEqual(
    findFirstValidationFocusTarget(
      { node_ids: ['missing', 'node_1'], edge_ids: ['edge_1'] },
      nodes,
      edges
    ),
    { type: 'node', id: 'node_1' }
  )

  assert.deepEqual(
    findFirstValidationFocusTarget(
      { node_ids: ['missing'], edge_ids: ['edge_1'] },
      nodes,
      edges
    ),
    { type: 'edge', id: 'edge_1' }
  )

  assert.equal(
    findFirstValidationFocusTarget(
      { node_ids: ['missing'], edge_ids: ['other'] },
      nodes,
      edges
    ),
    null
  )
})

test('getValidationCategoryText maps backend categories to Chinese labels', () => {
  assert.equal(getValidationCategoryText('structure_integrity'), '结构完整性')
  assert.equal(getValidationCategoryText('hierarchy_reasonableness'), '层级合理性')
  assert.equal(getValidationCategoryText('knowledge_graph_consistency'), '知识图谱一致性')
  assert.equal(getValidationCategoryText('logical_relation_conformity'), '逻辑关系规范性')
  assert.equal(getValidationCategoryText('unexpected_code'), '逻辑关系规范性')
})

test('withTemporarilyHiddenValidationFindings hides during export and restores afterwards', async () => {
  let visible = true
  const transitions = []

  const result = await withTemporarilyHiddenValidationFindings({
    getVisible: () => visible,
    setVisible: (next) => {
      visible = next
      transitions.push(next)
    },
    sync: async () => {
      transitions.push(`sync:${visible}`)
    },
    task: async () => {
      assert.equal(visible, false)
      return 'done'
    }
  })

  assert.equal(result, 'done')
  assert.equal(visible, true)
  assert.deepEqual(transitions, [false, 'sync:false', true, 'sync:true'])
})

test('withTemporarilyHiddenValidationFindings preserves already hidden state', async () => {
  let visible = false
  let syncCount = 0

  await withTemporarilyHiddenValidationFindings({
    getVisible: () => visible,
    setVisible: (next) => {
      visible = next
    },
    sync: async () => {
      syncCount += 1
    },
    task: async () => {
      assert.equal(visible, false)
    }
  })

  assert.equal(visible, false)
  assert.equal(syncCount, 0)
})