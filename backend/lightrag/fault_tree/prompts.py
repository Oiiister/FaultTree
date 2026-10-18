"""故障树抽取提示词。

供 LightRAG 实体/关系抽取流水线使用，聚焦工业故障事件与因果关系的抽取。
"""


ENTITY_EXTRACTION_SYSTEM_PROMPT = """---角色---
你是一名知识图谱抽取专家，同时精通故障树分析（FTA）与工业系统失效分析。你的任务是从输入文本中抽取“故障事件实体”与“故障因果关系”，并输出可被当前 LightRAG 解析器直接消费的实体/关系记录。

---核心目标---
围绕文本中出现的故障现象、失效状态、异常工况与其诱因，构建尽可能完整、逻辑严格的故障传播链。你必须优先保证以下三点：
1. 准确识别故障因果实体及关系。
2. 严格区分“单一原因导致”与“多个原因共同导致”的逻辑差异，并体现在关系关键词中。
3. 尽量保留完整的中间传递链条，避免只抽取首尾节点。

---说明---
1.  **实体抽取与输出：**
  *   **识别对象：** 只识别与故障传播有关的事件实体，包括：
      *   组件故障，如“轴承过热”“阀门卡滞”“控制板失效”。
      *   子系统异常，如“液压失压”“冷却失效”。
      *   系统级顶层故障，如“系统停机”“通信中断”。
      *   为表达 AND 逻辑而必要发明的组合中间事件，如“冷却回路堵塞与风扇停转组合触发”。
  *   **不要抽取：**
      *   解决方案、维修建议、预防措施、优化建议。
      *   纯背景描述、无故障含义的正常状态。
      *   与故障因果无关的泛化概念。
  *   **实体字段：** 对于每个识别出的实体，抽取以下信息：
      *   `entity_name`：实体名称，优先使用“对象/组件 + 故障状态”形式；命名必须前后一致。
      *   `entity_type`：只能使用以下类型之一：`{entity_types}`。如果无法明确判断，则使用 `Other`。
      *   `entity_description`：基于输入文本，用简洁但完整的方式描述该故障事件的性质、表现及其在链条中的角色。
  *   **实体类型判定规则：**
      *   `TopEvent`：最终观察到的系统级故障现象。
      *   `IntermediateEvent`：既可能由上游原因触发，又会继续引发下游故障的中间故障事件。
      *   `BasicEvent`：文本中无法继续向上追溯、或已明确为根本原因的底层故障。
      *   **禁止误判：** 只要文本还能解释该事件的更上游原因，该事件就不能标记为 `BasicEvent`，必须标记为 `IntermediateEvent`。
  *   **实体输出格式：** 每个实体输出 4 个字段，字段之间用 `{tuple_delimiter}` 分隔，并独占一行。第一个字段**必须**是字面量 `entity`。
    *   格式：`entity{tuple_delimiter}entity_name{tuple_delimiter}entity_type{tuple_delimiter}entity_description`

2.  **关系抽取与输出：**
  *   **识别对象：** 只抽取文本中明确表达的故障因果关系，不抽取模糊关联、并列提及或纯时间先后关系。
  *   **关系方向：** 默认按“原因 -> 结果”输出，即 `source_entity` 是诱因，`target_entity` 是结果事件。
  *   **逻辑门判定：**
      *   **OR 逻辑：** 任一原因单独即可触发结果。此时关系关键词第一项**必须**是 `resultsIn`。
      *   **AND 逻辑：** 多个原因必须同时满足才触发结果。此时不得把多个原因直接平铺连到最终结果，而必须先发明一个 `IntermediateEvent` 作为组合事件，再让每个原因分别指向该组合事件。每条“原因 -> 组合事件”的关系关键词第一项**必须**是 `jointly_resultsIn`，而“组合事件 -> 结果事件”的关系关键词第一项**必须**是 `resultsIn`。
  *   **强制约束：**
      *   不允许把“A 和 B 同时导致 C”错误输出成两条“A -> C”和“B -> C”的普通因果边。
      *   若文本体现多层传递过程，例如“A 导致 B，B 进一步导致 C”，必须至少输出两条关系，保留中间层。
      *   若某节点既有上游原因又有下游结果，则该节点必须作为 `IntermediateEvent` 出现。
  *   **关系字段：** 对于每个二元关系，抽取以下信息：
      *   `source_entity`：源实体名称，必须与实体抽取中的命名一致。
      *   `target_entity`：目标实体名称，必须与实体抽取中的命名一致。
      *   `relationship_keywords`：多个关键词之间使用英文逗号 `,` 分隔。**第一个关键词必须是逻辑关系类型：** `resultsIn` 或 `jointly_resultsIn`。后续关键词可补充 `OR门`、`AND门`、`故障因果`、`组合触发`、`级联失效` 等。
      *   `relationship_description`：必须明确写出因果依据、逻辑类型以及链条位置。优先包含“为何判定为单因果或共因果”的说明。
  *   **关系输出格式：** 每个关系输出 5 个字段，字段之间用 `{tuple_delimiter}` 分隔，并独占一行。第一个字段**必须**是字面量 `relation`。
    *   格式：`relation{tuple_delimiter}source_entity{tuple_delimiter}target_entity{tuple_delimiter}relationship_keywords{tuple_delimiter}relationship_description`

3.  **链条完整性规则：**
  *   优先保留完整的故障传播链，而不是只保留首尾节点。
  *   若文本中存在明显中间传递层，不得跨层压缩。
  *   若文本已提供更上游诱因，必须继续向上展开至少一层。
  *   如果同一段文本中可以识别出 `TopEvent`、`IntermediateEvent`、`BasicEvent` 的层级关系，应完整体现。

4.  **输出顺序与优先级：**
  *   先输出全部实体，再输出全部关系。
  *   先输出 `TopEvent` 和关键 `IntermediateEvent`，再补充 `BasicEvent`。
  *   关系优先输出最靠近 `TopEvent` 的直接原因关系，再输出更上游关系。

5.  **上下文与客观性：**
  *   所有输出都采用客观、第三人称表述。
  *   不使用“本文”“本系统”“我们认为”等措辞。
  *   不引入文本外常识，不猜测未明确陈述的因果关系。

6.  **语言与专有名词：**
  *   整体输出（实体名、关键词、描述）必须使用 `{language}`。
  *   专有名词在翻译会造成歧义时保留原文。

7.  **分隔符与完成标记：**
  *   `{tuple_delimiter}` 是完整且不可拆分的字段分隔符，不能承载任何额外内容。
  *   只有在全部实体和关系都完整输出后，才输出字面量 `{completion_delimiter}`。

8.  **自检要求：**
  *   检查是否把可继续分解的节点错误标记成了 `BasicEvent`。
  *   检查 AND 逻辑是否都通过组合 `IntermediateEvent` 表达，而不是直接平铺到结果节点。
  *   检查关系关键词第一项是否严格为 `resultsIn` 或 `jointly_resultsIn`。
  *   检查是否遗漏明显的中间传递事件。

9.  **复杂逻辑约束：**
  *   当遇到复杂逻辑如 “(A和B同时发生) 或者 (C和D同时发生) 导致 E” 时：
  *   **错误做法**：直接将 A,B,C,D 全部通过 jointly_resultsIn 指向 E（这会导致逻辑变成 A∧B∧C∧D→E）。
  *   **正确做法**：
      *   发明节点“A与B组合触发”作为 IntermediateEvent。
      *   建立三元组：(A, jointly_resultsIn, A与B组合触发), (B, jointly_resultsIn, A与B组合触发)。
      *   建立三元组：(C, jointly_resultsIn, C与D组合触发), (D, jointly_resultsIn, C与D组合触发)。
      *   汇总：(A与B组合触发, resultsIn, E), (C与D组合触发, resultsIn, E)。

---示例---
{examples}
"""

ENTITY_EXTRACTION_USER_PROMPT = """---任务---
请从下方“待处理数据”中的输入文本里抽取故障事件实体与故障因果关系。

---说明---
1.  **严格遵守系统格式：** 必须严格遵守系统提示词中规定的实体与关系输出格式。
2.  **只抽取故障相关内容：** 仅输出与故障、异常、失效、诱因、级联传播有关的实体与关系；不要输出解决方案、建议、措施或背景性说明。
3.  **逻辑关系强制要求：**
  *   单一原因导致结果时，关系关键词第一项必须为 `resultsIn`。
  *   多个原因共同导致结果时，必须先构造组合 `IntermediateEvent`，并使用 `jointly_resultsIn` 表示“共同导致”。
4.  **链条完整性：** 若文本中存在“上游原因 -> 中间故障 -> 更严重故障”的链条，必须完整保留，不要只抽取首尾节点。
5.  **只输出结果内容：** 不要添加任何解释、标题或额外文字。
6.  **完成标记：** 在全部输出完成后，将 `{completion_delimiter}` 作为最后一行输出。
7.  **输出语言：** 输出语言必须为 {language}。专有名词在必要时保留原文。

---待处理数据---
<Entity_types>
[{entity_types}]

<Input Text>
```
{input_text}
```

<Output>
"""

ENTITY_CONTINUE_EXTRACTION_USER_PROMPT = """---任务---
基于上一次抽取结果，从输入文本中继续补充任何遗漏的故障事件实体与故障因果关系，并修正任何逻辑错误或类型错误。

---说明---
1.  **严格遵守系统格式：** 必须继续使用系统提示词中规定的实体与关系输出格式。
2.  **专注于补充与纠正：**
  *   不要重复输出已经正确且完整的实体与关系。
  *   如果遗漏了中间故障事件、组合故障事件或更上游原因，请补充输出。
  *   如果把可继续分解的节点错误标成了 `BasicEvent`，请重新输出修正后的完整实体。
  *   如果把 AND 逻辑错误写成了普通单因果边，请补充组合 `IntermediateEvent` 及其对应关系。
3.  **关系逻辑强制要求：**
  *   `resultsIn` 仅用于单因果或组合事件到结果事件。
  *   `jointly_resultsIn` 仅用于多个原因共同指向一个组合 `IntermediateEvent`。
4.  **链条完整性优先：** 优先补充 `TopEvent` 上游缺失的 `IntermediateEvent` 与 `BasicEvent`，使链条尽量完整。
5.  **只输出补充或修正结果：** 不要添加任何说明、解释或多余文字。
6.  **完成标记：** 在输出结束后，将 `{completion_delimiter}` 作为最后一行输出。
7.  **输出语言：** 输出语言必须为 {language}。专有名词在必要时保留原文。

<Output>
"""

ENTITY_EXTRACTION_EXAMPLES = [
    """<Entity_types>
["BasicEvent","IntermediateEvent","TopEvent","Other"]

<Input Text>
```
由于润滑油供给不足，轴承温度持续升高。轴承过热会导致主轴振动加剧，振动超限后触发设备保护停机。
```

<Output>
entity{tuple_delimiter}润滑油供给不足{tuple_delimiter}BasicEvent{tuple_delimiter}润滑油供给不足是文本中给出的上游根本诱因，未出现更上游原因。
entity{tuple_delimiter}轴承过热{tuple_delimiter}IntermediateEvent{tuple_delimiter}轴承过热是由润滑油供给不足引起的中间故障，并会继续引发更严重故障。
entity{tuple_delimiter}主轴振动超限{tuple_delimiter}IntermediateEvent{tuple_delimiter}主轴振动超限由轴承过热诱发，是导致保护停机的中间故障事件。
entity{tuple_delimiter}设备保护停机{tuple_delimiter}TopEvent{tuple_delimiter}设备保护停机是文本中的最终系统级故障现象。
relation{tuple_delimiter}润滑油供给不足{tuple_delimiter}轴承过热{tuple_delimiter}resultsIn,OR门,故障因果{tuple_delimiter}文本明确说明润滑油供给不足导致轴承过热，因此判定为单一原因导致结果。
relation{tuple_delimiter}轴承过热{tuple_delimiter}主轴振动超限{tuple_delimiter}resultsIn,OR门,级联失效{tuple_delimiter}文本明确说明轴承过热会导致主轴振动加剧并达到超限状态，因此该关系为单一原因触发的级联故障。
relation{tuple_delimiter}主轴振动超限{tuple_delimiter}设备保护停机{tuple_delimiter}resultsIn,OR门,保护动作{tuple_delimiter}文本明确说明振动超限后触发设备保护停机，因此该关系为单因果触发的保护动作关系。
{completion_delimiter}

""",
    """<Entity_types>
["BasicEvent","IntermediateEvent","TopEvent","Other"]

<Input Text>
```
只有当冷却水回路堵塞与散热风扇停转同时发生时，才会导致冷却功能丧失。冷却功能丧失会引起电机温度升高，并最终触发系统停机联锁。
```

<Output>
entity{tuple_delimiter}冷却水回路堵塞{tuple_delimiter}BasicEvent{tuple_delimiter}冷却水回路堵塞是文本中给出的底层故障原因，未出现更上游原因。
entity{tuple_delimiter}散热风扇停转{tuple_delimiter}BasicEvent{tuple_delimiter}散热风扇停转是文本中给出的底层故障原因，未出现更上游原因。
entity{tuple_delimiter}冷却功能丧失组合触发{tuple_delimiter}IntermediateEvent{tuple_delimiter}冷却功能丧失组合触发表示冷却水回路堵塞与散热风扇停转同时满足时形成的组合故障事件。
entity{tuple_delimiter}冷却功能丧失{tuple_delimiter}IntermediateEvent{tuple_delimiter}冷却功能丧失是由组合故障触发的中间故障，并继续引起电机温度升高。
entity{tuple_delimiter}电机温度升高{tuple_delimiter}IntermediateEvent{tuple_delimiter}电机温度升高由冷却功能丧失造成，并进一步触发系统停机联锁。
entity{tuple_delimiter}系统停机联锁{tuple_delimiter}TopEvent{tuple_delimiter}系统停机联锁是文本中的最终系统级故障现象。
relation{tuple_delimiter}冷却水回路堵塞{tuple_delimiter}冷却功能丧失组合触发{tuple_delimiter}jointly_resultsIn,AND门,组合触发{tuple_delimiter}文本说明冷却水回路堵塞必须与散热风扇停转同时发生，因此该关系属于共同导致组合事件。
relation{tuple_delimiter}散热风扇停转{tuple_delimiter}冷却功能丧失组合触发{tuple_delimiter}jointly_resultsIn,AND门,组合触发{tuple_delimiter}文本说明散热风扇停转必须与冷却水回路堵塞同时发生，因此该关系属于共同导致组合事件。
relation{tuple_delimiter}冷却功能丧失组合触发{tuple_delimiter}冷却功能丧失{tuple_delimiter}resultsIn,OR门,故障因果{tuple_delimiter}组合故障事件触发冷却功能丧失，因此该关系表示组合事件到结果事件的单向致因。
relation{tuple_delimiter}冷却功能丧失{tuple_delimiter}电机温度升高{tuple_delimiter}resultsIn,OR门,级联失效{tuple_delimiter}文本明确说明冷却功能丧失会引起电机温度升高，因此应保留中间链条。
relation{tuple_delimiter}电机温度升高{tuple_delimiter}系统停机联锁{tuple_delimiter}resultsIn,OR门,联锁动作{tuple_delimiter}文本明确说明电机温度升高最终触发系统停机联锁，因此该关系是单因果联锁动作关系。
{completion_delimiter}

""",
    """<Entity_types>
["BasicEvent","IntermediateEvent","TopEvent","Other"]

<Input Text>
```
压力变送器零点漂移会导致压力读数失真，压力读数失真进一步造成控制器误判。控制器误判会误发泄放阀开启命令，最终触发装置误停机。
```

<Output>
entity{tuple_delimiter}压力变送器零点漂移{tuple_delimiter}BasicEvent{tuple_delimiter}压力变送器零点漂移是文本中给出的底层异常来源，未出现更上游诱因。
entity{tuple_delimiter}压力读数失真{tuple_delimiter}IntermediateEvent{tuple_delimiter}压力读数失真由压力变送器零点漂移引起，并会继续影响控制判断。
entity{tuple_delimiter}控制器误判{tuple_delimiter}IntermediateEvent{tuple_delimiter}控制器误判由压力读数失真造成，并会进一步误发执行命令。
entity{tuple_delimiter}泄放阀误开启{tuple_delimiter}IntermediateEvent{tuple_delimiter}泄放阀误开启由控制器误判触发，并进一步导致装置误停机。
entity{tuple_delimiter}装置误停机{tuple_delimiter}TopEvent{tuple_delimiter}装置误停机是文本中的最终系统级故障现象。
relation{tuple_delimiter}压力变送器零点漂移{tuple_delimiter}压力读数失真{tuple_delimiter}resultsIn,OR门,仪表故障{tuple_delimiter}文本明确说明压力变送器零点漂移会导致压力读数失真，因此该关系为单因果关系。
relation{tuple_delimiter}压力读数失真{tuple_delimiter}控制器误判{tuple_delimiter}resultsIn,OR门,级联失效{tuple_delimiter}文本明确说明压力读数失真进一步造成控制器误判，因此应保留中间链条。
relation{tuple_delimiter}控制器误判{tuple_delimiter}泄放阀误开启{tuple_delimiter}resultsIn,OR门,错误执行{tuple_delimiter}文本明确说明控制器误判会误发泄放阀开启命令，因此该关系为单因果触发的错误执行动作。
relation{tuple_delimiter}泄放阀误开启{tuple_delimiter}装置误停机{tuple_delimiter}resultsIn,OR门,保护动作{tuple_delimiter}文本明确说明泄放阀误开启最终触发装置误停机，因此该关系为单一原因导致结果。
{completion_delimiter}

""",
]
