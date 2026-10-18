import { expect, test } from '@playwright/test'

const FAULT_TREE_DRAFT_STORAGE_KEY = 'LIGHTRAG-FAULT-TREE-DRAFT'
const FAULT_TREE_DRAFT_STORAGE_VERSION = 1

const buildMinimalFaultTreeDraft = () => ({
  version: FAULT_TREE_DRAFT_STORAGE_VERSION,
  zoomPercent: 100,
  inputText: '主泵失效',
  uploadState: {
    fileName: '',
    status: 'idle',
    progress: 0,
    text: ''
  },
  lastGeneratedTriplets: [],
  lastGeneratedSourceLabel: '',
  histories: [],
  selectedHistoryId: '',
  nodes: [
    { id: 'top_1', label: '主泵失效', type: 'top', probability: 0.001, source: '', updatedAt: null, x: 380, y: 110 },
    { id: 'gate_1', type: 'gate', gate: 'OR', parentId: 'top_1', updatedAt: null, x: 430, y: 255 },
    { id: 'basic_1', label: '供电异常', type: 'basic', probability: 0.001, source: '', updatedAt: null, x: 250, y: 410 },
    { id: 'basic_2', label: '机械卡滞', type: 'basic', probability: 0.001, source: '', updatedAt: null, x: 610, y: 410 }
  ],
  edges: [
    { id: 'edge_1', source: 'top_1', target: 'gate_1', style: { color: '#fbbf24', width: 4 } },
    { id: 'edge_2', source: 'gate_1', target: 'basic_1', style: { color: '#22d3ee', width: 4 } },
    { id: 'edge_3', source: 'gate_1', target: 'basic_2', style: { color: '#22d3ee', width: 4 } }
  ],
  updatedAt: Date.now()
})

const buildInvalidFaultTreeDraft = () => ({
  version: FAULT_TREE_DRAFT_STORAGE_VERSION,
  zoomPercent: 100,
  inputText: '主泵失效',
  uploadState: {
    fileName: '',
    status: 'idle',
    progress: 0,
    text: ''
  },
  lastGeneratedTriplets: [],
  lastGeneratedSourceLabel: '',
  histories: [],
  selectedHistoryId: '',
  nodes: [
    { id: 'top_1', label: '主泵失效', type: 'top', probability: 0.001, source: '', updatedAt: null, x: 380, y: 110 },
    { id: 'basic_1', label: '供电异常', type: 'basic', probability: 0.001, source: '', updatedAt: null, x: 250, y: 320 }
  ],
  edges: [
    { id: 'edge_1', source: 'top_1', target: 'basic_1', style: { color: '#22d3ee', width: 4 } }
  ],
  updatedAt: Date.now()
})

const buildConnectableFaultTreeDraft = () => ({
  version: FAULT_TREE_DRAFT_STORAGE_VERSION,
  zoomPercent: 100,
  inputText: '主泵失效',
  uploadState: {
    fileName: '',
    status: 'idle',
    progress: 0,
    text: ''
  },
  lastGeneratedTriplets: [],
  lastGeneratedSourceLabel: '',
  histories: [],
  selectedHistoryId: '',
  nodes: [
    { id: 'top_1', label: '主泵失效', type: 'top', probability: 0.001, source: '', updatedAt: null, x: 380, y: 110 },
    { id: 'gate_1', type: 'gate', gate: 'OR', parentId: 'top_1', updatedAt: null, x: 430, y: 255 },
    { id: 'basic_1', label: '供电异常', type: 'basic', probability: 0.001, source: '', updatedAt: null, x: 250, y: 410 },
    { id: 'middle_1', label: '液压波动', type: 'middle', probability: 0.001, source: '', updatedAt: null, x: 610, y: 410 }
  ],
  edges: [
    { id: 'edge_1', source: 'top_1', target: 'gate_1', style: { color: '#fbbf24', width: 4 } },
    { id: 'edge_2', source: 'gate_1', target: 'basic_1', style: { color: '#22d3ee', width: 4 } }
  ],
  updatedAt: Date.now()
})

const buildInvalidValidationResponse = () => ({
  summary: {
    valid: false,
    total_issues: 1,
    error_count: 1,
    warning_count: 0,
    category_counts: {
      logical_relation_conformity: 1
    }
  },
  issues: [
    {
      category: 'logical_relation_conformity',
      code: 'event_to_event_connection',
      severity: 'error',
      message: '连线 edge_1 将事件直接连接到事件。',
      suggestion: '请在“主泵失效”和“供电异常”之间插入一个逻辑门，以明确两者之间的逻辑关系。',
      suggestion_source: 'rule',
      node_ids: ['top_1', 'basic_1'],
      edge_ids: ['edge_1']
    }
  ]
})

const buildGenerationTripletsJson = () => JSON.stringify([
  {
    object_name: '系统停机',
    object_type: 'TopEvent',
    subject_name: '供电异常',
    subject_type: 'IntermediateEvent',
    relation: 'CausedBy',
    confidence: 0.92,
    source: 'test'
  },
  {
    object_name: '供电异常',
    object_type: 'IntermediateEvent',
    subject_name: '保险丝熔断',
    subject_type: 'BasicEvent',
    relation: 'CausedBy',
    confidence: 0.88,
    source: 'test'
  }
])

const readRenderedTreeSnapshot = async (page) => {
  return page.evaluate(() => {
    const root = document.querySelector('.c-tree-stage')
    const nodeElements = Array.from(root?.querySelectorAll?.('[data-node-id]') || [])
    const edgeGroupCount = root?.querySelectorAll?.('svg > g').length || 0
    const edgeElements = Array.from(root?.querySelectorAll?.('svg > g > path') || [])

    const nodes = nodeElements
      .map((element) => ({
        id: element.getAttribute('data-node-id') || '',
        left: element instanceof HTMLElement ? element.style.left : '',
        top: element instanceof HTMLElement ? element.style.top : ''
      }))
      .sort((a, b) => a.id.localeCompare(b.id))

    const edges = edgeElements
      .filter((element) => element.getAttribute('stroke') && element.getAttribute('stroke') !== 'transparent')
      .map((element) => ({
        d: element.getAttribute('d') || '',
        stroke: element.getAttribute('stroke') || '',
        width: element.getAttribute('stroke-width') || ''
      }))
      .sort((a, b) => a.d.localeCompare(b.d) || a.stroke.localeCompare(b.stroke) || a.width.localeCompare(b.width))

    return { nodes, edges, edgeGroupCount }
  })
}

test.describe('Fault tree smoke', () => {
  test('restores a minimal fault tree draft and opens validation results after checking', async ({ page }) => {
    await page.addInitScript((draft) => {
      window.localStorage.setItem('LIGHTRAG-FAULT-TREE-DRAFT', JSON.stringify(draft))
    }, buildMinimalFaultTreeDraft())

    await page.goto('/webui')

    await expect(page.getByRole('tab', { name: '故障树' })).toBeVisible()
    await page.getByRole('tab', { name: '故障树' }).click()

    await expect(page.getByText('故障树生成工作台')).toBeVisible()
    const validateButton = page.getByRole('button', { name: '检验' })
    await expect(validateButton).toBeVisible()
    await expect(validateButton).toBeEnabled()
    await expect(page.getByText('专家辅助系统 - Expert Assistant')).toBeVisible()

    const validationResponsePromise = page.waitForResponse(
      (response) => response.url().includes('/fault-tree/validate') && response.request().method() === 'POST' && response.status() === 200
    )

    await validateButton.click()
    await validationResponsePromise

    await expect(page.getByText('故障树检查结果')).toBeVisible()
    await expect(page.getByText('已完成结构、层级与逻辑关系规范性检查，重新检验会覆盖当前结果。')).toBeVisible()
  })

  test('marks validation results as stale after the tree is edited', async ({ page }) => {
    await page.addInitScript((draft) => {
      window.localStorage.setItem('LIGHTRAG-FAULT-TREE-DRAFT', JSON.stringify(draft))
    }, buildMinimalFaultTreeDraft())

    await page.goto('/webui')

    await page.getByRole('tab', { name: '故障树' }).click()

    const validateButton = page.getByRole('button', { name: '检验' })
    await expect(validateButton).toBeEnabled()

    const validationResponsePromise = page.waitForResponse(
      (response) => response.url().includes('/fault-tree/validate') && response.request().method() === 'POST' && response.status() === 200
    )

    await validateButton.click()
    await validationResponsePromise

    await expect(page.getByText('故障树检查结果')).toBeVisible()

    const nodeButton = page.getByRole('button', { name: /节点 供电异常/ })
    await expect(nodeButton).toBeVisible()
    await nodeButton.click()

    await expect(page.getByText('Selected: 供电异常')).toBeVisible()

    await page.keyboard.press('Delete')

    await expect(page.getByText('结果已过期')).toBeVisible()
    await expect(page.getByText('你在检验后修改了故障树，当前建议和高亮仅供参考，建议重新检验。')).toBeVisible()
    await expect(page.getByRole('button', { name: '重新检验' })).toBeVisible()
  })

  test('renders validation issue categories without crashing on invalid trees', async ({ page }) => {
    await page.addInitScript((draft) => {
      window.localStorage.setItem('LIGHTRAG-FAULT-TREE-DRAFT', JSON.stringify(draft))
    }, buildInvalidFaultTreeDraft())

    await page.route('**/fault-tree/validate', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(buildInvalidValidationResponse())
      })
    })

    await page.goto('/webui')

    await page.getByRole('tab', { name: '故障树' }).click()

    const validateButton = page.getByRole('button', { name: '检验' })
    await expect(validateButton).toBeEnabled()

    const validationResponsePromise = page.waitForResponse(
      (response) => response.url().includes('/fault-tree/validate') && response.request().method() === 'POST' && response.status() === 200
    )

    await validateButton.click()
    await validationResponsePromise

    await expect(page.getByText('故障树检查结果')).toBeVisible()
    await expect(page.getByText('逻辑关系规范性', { exact: true })).toBeVisible()
    await expect(page.getByText('连线 edge_1 将事件直接连接到事件。')).toBeVisible()
  })

  test('does not modify rendered nodes or edges during validation', async ({ page }) => {
    await page.addInitScript((draft) => {
      window.localStorage.setItem('LIGHTRAG-FAULT-TREE-DRAFT', JSON.stringify(draft))
    }, buildMinimalFaultTreeDraft())

    await page.route('**/fault-tree/validate', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          summary: {
            valid: true,
            total_issues: 0,
            error_count: 0,
            warning_count: 0,
            category_counts: {}
          },
          issues: []
        })
      })
    })

    await page.goto('/webui')
    await page.getByRole('tab', { name: '故障树' }).click()

    const beforeSnapshot = await readRenderedTreeSnapshot(page)
    const validateButton = page.getByRole('button', { name: '检验' })
    await expect(validateButton).toBeEnabled()

    const validationResponsePromise = page.waitForResponse(
      (response) => response.url().includes('/fault-tree/validate') && response.request().method() === 'POST' && response.status() === 200
    )

    await validateButton.click()
    await validationResponsePromise
    await expect(page.getByText('故障树检查结果')).toBeVisible()

    const afterSnapshot = await readRenderedTreeSnapshot(page)

    expect(afterSnapshot).toEqual(beforeSnapshot)
  })

  test('undo restores the previous tree after generating from uploaded json', async ({ page }) => {
    await page.addInitScript((draft) => {
      window.localStorage.setItem('LIGHTRAG-FAULT-TREE-DRAFT', JSON.stringify(draft))
    }, buildMinimalFaultTreeDraft())

    await page.goto('/webui')
    await page.getByRole('tab', { name: '故障树' }).click()

    const beforeSnapshot = await readRenderedTreeSnapshot(page)

    await page.locator('input[type="file"]').setInputFiles({
      name: 'triplets.json',
      mimeType: 'application/json',
      buffer: Buffer.from(buildGenerationTripletsJson(), 'utf-8')
    })

    const generateButton = page.getByRole('button', { name: '生成' })
    await expect(generateButton).toBeEnabled()
    await generateButton.click()

    let generatedSnapshot = null
    await expect.poll(async () => {
      const snapshot = await readRenderedTreeSnapshot(page)
      generatedSnapshot = snapshot
      return JSON.stringify(snapshot) === JSON.stringify(beforeSnapshot)
    }).toBe(false)

    const undoButton = page.getByRole('button', { name: '撤销' })
    await expect(undoButton).toBeEnabled()
    await undoButton.click()

    await expect.poll(async () => {
      const snapshot = await readRenderedTreeSnapshot(page)
      return JSON.stringify(snapshot)
    }).toBe(JSON.stringify(beforeSnapshot))

    const redoButton = page.getByRole('button', { name: '重做' })
    await expect(redoButton).toBeEnabled()
    await redoButton.click()

    await expect.poll(async () => {
      const snapshot = await readRenderedTreeSnapshot(page)
      return JSON.stringify(snapshot)
    }).toBe(JSON.stringify(generatedSnapshot))
  })

  test('undo after creating an edge restores the previous graph without relayout deformation', async ({ page }) => {
    await page.addInitScript((draft) => {
      window.localStorage.setItem('LIGHTRAG-FAULT-TREE-DRAFT', JSON.stringify(draft))
    }, buildConnectableFaultTreeDraft())

    await page.goto('/webui')
    await page.getByRole('tab', { name: '故障树' }).click()

    const beforeSnapshot = await readRenderedTreeSnapshot(page)

    await page.locator('[data-node-id="gate_1"][data-handle="out"]').evaluate((element) => {
      element.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
    })
    await page.locator('.c-node[data-node-id="middle_1"]').evaluate((element) => {
      element.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
    })

    await expect.poll(async () => {
      const snapshot = await readRenderedTreeSnapshot(page)
      return snapshot.edgeGroupCount
    }).toBe(beforeSnapshot.edgeGroupCount + 1)

    const generatedEdgeSnapshot = await readRenderedTreeSnapshot(page)
    expect(generatedEdgeSnapshot.nodes).toEqual(beforeSnapshot.nodes)

    const undoButton = page.getByRole('button', { name: '撤销' })
    await expect(undoButton).toBeEnabled()
    await undoButton.click()

    await expect.poll(async () => {
      const snapshot = await readRenderedTreeSnapshot(page)
      return snapshot.edges.length
    }).toBe(beforeSnapshot.edges.length)

    const afterUndoSnapshot = await readRenderedTreeSnapshot(page)
    expect(afterUndoSnapshot.nodes).toEqual(beforeSnapshot.nodes)
  })

  test('deleting the parent to OR edge does not move nodes and undo restores the exact graph', async ({ page }) => {
    await page.addInitScript((draft) => {
      window.localStorage.setItem('LIGHTRAG-FAULT-TREE-DRAFT', JSON.stringify(draft))
    }, buildMinimalFaultTreeDraft())

    await page.goto('/webui')
    await page.getByRole('tab', { name: '故障树' }).click()

    const beforeSnapshot = await readRenderedTreeSnapshot(page)

    await page.locator('.c-tree-stage svg > g path[stroke="#fbbf24"]').first().evaluate((element) => {
      element.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
    })

    const deleteButton = page.getByRole('button', { name: '删除' }).first()
    await expect(deleteButton).toBeEnabled()
    await deleteButton.click()

    await expect.poll(async () => {
      const snapshot = await readRenderedTreeSnapshot(page)
      return snapshot.edgeGroupCount
    }).toBe(beforeSnapshot.edgeGroupCount - 1)

    const afterDeleteSnapshot = await readRenderedTreeSnapshot(page)
    expect(afterDeleteSnapshot.nodes).toEqual(beforeSnapshot.nodes)

    const undoButton = page.getByRole('button', { name: '撤销' })
    await expect(undoButton).toBeEnabled()
    await undoButton.click()

    await expect.poll(async () => {
      const snapshot = await readRenderedTreeSnapshot(page)
      return snapshot.edgeGroupCount
    }).toBe(beforeSnapshot.edgeGroupCount)

    const afterUndoSnapshot = await readRenderedTreeSnapshot(page)
    expect(afterUndoSnapshot.nodes).toEqual(beforeSnapshot.nodes)
  })

  test('marks results as stale when the tree changes before validation returns', async ({ page }) => {
    await page.addInitScript((draft) => {
      window.localStorage.setItem('LIGHTRAG-FAULT-TREE-DRAFT', JSON.stringify(draft))
    }, buildMinimalFaultTreeDraft())

    await page.route('**/fault-tree/validate', async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 400))
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          summary: {
            valid: true,
            total_issues: 0,
            error_count: 0,
            warning_count: 0,
            category_counts: {}
          },
          issues: []
        })
      })
    })

    await page.goto('/webui')
    await page.getByRole('tab', { name: '故障树' }).click()

    const validateButton = page.getByRole('button', { name: '检验' })
    await expect(validateButton).toBeEnabled()

    const validationResponsePromise = page.waitForResponse(
      (response) => response.url().includes('/fault-tree/validate') && response.request().method() === 'POST' && response.status() === 200
    )

    await validateButton.click()

    const nodeButton = page.getByRole('button', { name: /节点 供电异常/ })
    await expect(nodeButton).toBeVisible()
    await nodeButton.click()
    await expect(page.getByText('Selected: 供电异常')).toBeVisible()
    await page.keyboard.press('Delete')

    await validationResponsePromise

    await expect(page.getByText('故障树检查结果')).toBeVisible()
    await expect(page.getByText('结果已过期')).toBeVisible()
    await expect(page.getByText('你在检验后修改了故障树，当前建议和高亮仅供参考，建议重新检验。')).toBeVisible()
  })

  test.afterEach(async ({ page }) => {
    await page.evaluate((storageKey) => {
      window.localStorage.removeItem(storageKey)
    }, FAULT_TREE_DRAFT_STORAGE_KEY)
  })
})