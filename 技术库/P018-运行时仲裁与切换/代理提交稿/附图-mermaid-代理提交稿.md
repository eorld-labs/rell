# 附图 Mermaid 稿

> 本文档用于集中存放说明书附图的 Mermaid 绘图稿。附图采用黑白线框风格，便于后续导出为正式附图或交由代理人重绘。

> 附图中的节点文字、步骤编号、字段表达和部署位置仅为示例性说明；实际实施方式可采用不同名称、编号、消息格式、字段结构或部署结构。

## 图 1 状态优先任务交互仲裁方法总体流程图

```mermaid
%%{init: {'flowchart': {'htmlLabels': true}, 'theme': 'base', 'themeVariables': { 'primaryColor':'#ffffff', 'primaryBorderColor':'#000000', 'background':'#ffffff', 'mainBkg':'#ffffff', 'clusterBkg':'#ffffff', 'clusterBorder':'#000000', 'lineColor':'#000000', 'tertiaryColor':'#ffffff', 'fontSize':'16px'}}}%%
graph TD
    A["自动化执行体处于<br/>任务执行期间"] --> B["S101 接收交互输入"]
    B --> C["S102 改变执行控制行为之前<br/>读取任务期运行时世界状态快照"]
    C --> D["S103 基于交互输入和快照<br/>判定输入类型"]
    D --> E{"状态查询输入<br/>还是任务控制输入"}
    E -->|状态查询| F["S104 基于快照<br/>输出状态响应"]
    E -->|任务控制| G["S105 判定对当前任务<br/>的影响并输出仲裁结果<br/>继续/暂停/暂停切换/合并/终止/确认"]
    G --> H{"是否允许继续<br/>合并或切换"}
    H -->|是| I["S106 基于当前事实<br/>生成后续待执行步骤集合<br/>排除已满足/已完成/已成立步骤"]
    H -->|否| J["暂停/终止/人工确认"]
    I --> K["S107 交由执行控制链路<br/>继续执行"]
    K --> L["S108 任务完成/取消/终止<br/>或释放条件成立时释放快照"]
    J -->|终止或释放条件成立| L

    style A fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style B fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style C fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style D fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style E fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style F fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style G fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style H fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style I fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style J fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style K fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style L fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
```

## 图 2 系统结构图

```mermaid
%%{init: {'flowchart': {'htmlLabels': true}, 'theme': 'base', 'themeVariables': { 'primaryColor':'#ffffff', 'primaryBorderColor':'#000000', 'background':'#ffffff', 'mainBkg':'#ffffff', 'clusterBkg':'#ffffff', 'clusterBorder':'#000000', 'lineColor':'#000000', 'tertiaryColor':'#ffffff', 'fontSize':'16px'}}}%%
graph TD
    A["交互输入"] --> B["交互接收单元"]
    B --> C["状态快照读取单元"]
    C --> D["任务期运行时<br/>世界状态快照"]
    D --> E["输入判定单元"]
    B --> E
    E --> F{"状态查询<br/>还是任务控制"}
    F -->|状态查询| G["状态响应输出"]
    F -->|任务控制| H["仲裁单元"]
    H --> I["仲裁结果<br/>继续/暂停/暂停切换<br/>合并/终止/人工确认"]
    I --> J["续推控制单元"]
    J --> K["后续待执行步骤集合"]
    K --> L["执行控制链路"]
    L --> M["自动化执行体"]
    M -.->|状态反馈| D
    M --> O["任务完成/取消/终止<br/>或释放条件成立"]
    O --> N["状态释放单元"]
    N -->|删除或释放| D

    style A fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style B fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style C fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style D fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style E fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style F fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style G fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style H fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style I fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style J fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style K fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style L fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style M fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style N fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style O fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
```

## 图 3 任务期运行时世界状态快照数据结构示意图

```mermaid
%%{init: {'flowchart': {'htmlLabels': true}, 'theme': 'base', 'themeVariables': { 'primaryColor':'#ffffff', 'primaryBorderColor':'#000000', 'background':'#ffffff', 'mainBkg':'#ffffff', 'clusterBkg':'#ffffff', 'clusterBorder':'#000000', 'lineColor':'#000000', 'tertiaryColor':'#ffffff', 'fontSize':'16px'}}}%%
graph TD
    A["任务期运行时<br/>世界状态快照"] --> B["当前语义区域"]
    A --> C["持有对象"]
    A --> D["已成立事实"]
    A --> E["待验证事实"]
    A --> F["当前步骤"]
    A --> G["当前任务目标"]
    A --> H["活动约束"]
    A --> I["挂起任务标识<br/>及挂起任务进度"]
    A --> J["快照版本/时间戳"]

    style A fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style B fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style C fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style D fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style E fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style F fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style G fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style H fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style I fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style J fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
```

## 图 4 状态查询输入处理流程图

```mermaid
%%{init: {'flowchart': {'htmlLabels': true}, 'theme': 'base', 'themeVariables': { 'primaryColor':'#ffffff', 'primaryBorderColor':'#000000', 'background':'#ffffff', 'mainBkg':'#ffffff', 'clusterBkg':'#ffffff', 'clusterBorder':'#000000', 'lineColor':'#000000', 'tertiaryColor':'#ffffff', 'fontSize':'16px'}}}%%
graph TD
    A["接收交互输入"] --> B["读取任务期快照"]
    B --> C{"判定为<br/>状态查询输入"}
    C -->|是| D["定位查询对象<br/>或查询字段"]
    D --> E["从快照读取<br/>对应事实或字段"]
    E --> F["生成状态响应"]
    F --> G["输出状态响应<br/>及状态依据"]
    C -->|否| H["进入任务控制<br/>仲裁流程"]

    style A fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style B fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style C fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style D fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style E fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style F fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style G fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style H fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
```

## 图 5 任务控制输入仲裁流程图

```mermaid
%%{init: {'flowchart': {'htmlLabels': true}, 'theme': 'base', 'themeVariables': { 'primaryColor':'#ffffff', 'primaryBorderColor':'#000000', 'background':'#ffffff', 'mainBkg':'#ffffff', 'clusterBkg':'#ffffff', 'clusterBorder':'#000000', 'lineColor':'#000000', 'tertiaryColor':'#ffffff', 'fontSize':'16px'}}}%%
graph TD
    A["交互输入判定为<br/>任务控制输入"] --> B["读取任务期快照中的<br/>持物状态/当前步骤<br/>任务目标/活动约束"]
    B --> C["判定输入对当前任务<br/>待执行步骤序列的影响"]
    C --> D{"仲裁判定"}
    D --> E["继续当前任务"]
    D --> F["暂停当前任务"]
    D --> G["暂停并切换任务"]
    D --> H["合并入当前任务"]
    D --> I["终止当前任务"]
    D --> J["请求人工确认"]
    E --> K["进入续推控制"]
    G --> K
    H --> K
    F --> L["记录挂起状态"]
    I --> M["进入终止流程"]
    J --> N["等待人工确认"]

    style A fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style B fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style C fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style D fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style E fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style F fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style G fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style H fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style I fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style J fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style K fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style L fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style M fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style N fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
```

## 图 6 基于当前事实裁剪后续步骤流程图

```mermaid
%%{init: {'flowchart': {'htmlLabels': true}, 'theme': 'base', 'themeVariables': { 'primaryColor':'#ffffff', 'primaryBorderColor':'#000000', 'background':'#ffffff', 'mainBkg':'#ffffff', 'clusterBkg':'#ffffff', 'clusterBorder':'#000000', 'lineColor':'#000000', 'tertiaryColor':'#ffffff', 'fontSize':'16px'}}}%%
graph TD
    A["仲裁允许继续/合并/切换"] --> B["获取候选步骤链"]
    B --> C["读取任务期快照中的<br/>当前事实"]
    C --> D["逐步骤比对"]
    D --> E{"执行前提事实<br/>是否已满足"}
    E -->|是| F["排除该步骤"]
    E -->|否| G["保留该步骤"]
    D --> H{"目标事实<br/>是否已成立"}
    H -->|是| F
    H -->|否| G
    D --> I{"步骤是否<br/>已执行完成"}
    I -->|是| F
    I -->|否| G
    F --> J["标记为已裁剪"]
    G --> K["加入后续待执行<br/>步骤集合"]
    J --> L["输出后续待执行<br/>步骤集合"]
    K --> L

    style A fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style B fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style C fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style D fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style E fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style F fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style G fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style H fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style I fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style J fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style K fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style L fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
```

## 图 7 当前持有对象与新任务目标冲突仲裁示意图

```mermaid
%%{init: {'flowchart': {'htmlLabels': true}, 'theme': 'base', 'themeVariables': { 'primaryColor':'#ffffff', 'primaryBorderColor':'#000000', 'background':'#ffffff', 'mainBkg':'#ffffff', 'clusterBkg':'#ffffff', 'clusterBorder':'#000000', 'lineColor':'#000000', 'tertiaryColor':'#ffffff', 'fontSize':'16px'}}}%%
graph TD
    A["接收任务控制输入<br/>新任务切换请求"] --> B["读取任务期快照"]
    B --> C{"检查持有对象字段"}
    C -->|未持有| D["继续仲裁流程<br/>允许切换"]
    C -->|当前持有对象| E{"新任务目标的对象<br/>区域或状态是否已确认"}
    E -->|已确认且不冲突| D
    E -->|未确认或冲突| F["输出仲裁结果"]
    F --> G["请求人工确认"]
    F --> H["要求先释放当前持有对象"]
    F --> I["暂停当前任务"]
    F --> J["终止当前任务"]

    style A fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style B fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style C fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style D fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style E fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style F fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style G fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style H fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style I fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style J fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
```

## 图 8 任务暂停、恢复与快照续推示意图

```mermaid
%%{init: {'flowchart': {'htmlLabels': true}, 'theme': 'base', 'themeVariables': { 'primaryColor':'#ffffff', 'primaryBorderColor':'#000000', 'background':'#ffffff', 'mainBkg':'#ffffff', 'clusterBkg':'#ffffff', 'clusterBorder':'#000000', 'lineColor':'#000000', 'tertiaryColor':'#ffffff', 'fontSize':'16px'}}}%%
graph TD
    A["仲裁结果：暂停当前任务"] --> B["记录活动任务标识<br/>已执行进度<br/>已成立事实<br/>持有对象状态"]
    B --> C["任务进入挂起状态"]
    C --> D["接收恢复指令"]
    D --> E["读取恢复时刻的<br/>任务期运行时世界状态快照"]
    E --> F{"恢复时刻的<br/>环境是否变化"}
    F -->|未变化| G["以恢复时刻快照<br/>为续推起点<br/>不以任务初始状态重跑"]
    F -->|已变化| H["请求重新确认对象<br/>输出不可继续<br/>或触发替代步骤"]
    G --> I["生成后续待执行<br/>步骤集合"]

    style A fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style B fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style C fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style D fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style E fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style F fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style G fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style H fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style I fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
```

## 图 9 约束追加输入和教学输入合并流程图

```mermaid
%%{init: {'flowchart': {'htmlLabels': true}, 'theme': 'base', 'themeVariables': { 'primaryColor':'#ffffff', 'primaryBorderColor':'#000000', 'background':'#ffffff', 'mainBkg':'#ffffff', 'clusterBkg':'#ffffff', 'clusterBorder':'#000000', 'lineColor':'#000000', 'tertiaryColor':'#ffffff', 'fontSize':'16px'}}}%%
graph TD
    A["接收约束追加输入<br/>或教学输入"] --> B["转换为候选约束<br/>候选步骤<br/>候选目标事实<br/>或候选澄清问题"]
    B --> C["读取任务期快照"]
    C --> D{"判断是否可<br/>合并入当前任务"}
    D -->|与当前目标一致<br/>不违反当前事实| E["输出仲裁结果<br/>合并入当前任务"]
    D -->|与当前目标冲突<br/>或缺少对象指认| F["输出待确认内容<br/>或澄清问题"]
    E --> G["更新当前任务<br/>约束或步骤"]
    F --> H["请求人工确认<br/>或澄清"]

    style A fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style B fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style C fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style D fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style E fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style F fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style G fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style H fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
```

## 图 10 云端、边缘端、端侧与执行体本体的分布式部署示意图

```mermaid
%%{init: {'flowchart': {'htmlLabels': true}, 'theme': 'base', 'themeVariables': { 'primaryColor':'#ffffff', 'primaryBorderColor':'#000000', 'background':'#ffffff', 'mainBkg':'#ffffff', 'clusterBkg':'#ffffff', 'clusterBorder':'#000000', 'lineColor':'#000000', 'tertiaryColor':'#ffffff', 'fontSize':'16px'}}}%%
graph TD
    subgraph 云端
    A["仲裁单元"]
    B["可选云端候选服务<br/>或经验库"]
    end
    subgraph 边缘端
    C["输入判定单元"]
    D["续推控制单元"]
    end
    subgraph 用户终端
    E["交互接收单元"]
    end
    subgraph 执行体本体
    F["状态快照读取单元"]
    G["状态释放单元"]
    H["执行控制链路"]
    I["自动化执行体"]
    end
    E -->|交互输入| C
    F -->|快照数据| C
    C -->|判定结果| A
    A -->|仲裁结果| D
    D -->|后续步骤集合| H
    H --> I
    I -.->|状态反馈| F
    G -->|释放指令| F
    B -.->|候选或经验支持| A

    style A fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style B fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style C fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style D fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style E fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style F fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style G fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style H fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style I fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
```

## 图 11 任务期快照释放与防状态污染示意图

```mermaid
%%{init: {'flowchart': {'htmlLabels': true}, 'theme': 'base', 'themeVariables': { 'primaryColor':'#ffffff', 'primaryBorderColor':'#000000', 'background':'#ffffff', 'mainBkg':'#ffffff', 'clusterBkg':'#ffffff', 'clusterBorder':'#000000', 'lineColor':'#000000', 'tertiaryColor':'#ffffff', 'fontSize':'16px'}}}%%
graph TD
    A["任务完成/取消/终止<br/>或释放条件成立"] --> B["触发快照释放流程"]
    B --> C["删除或释放<br/>任务期运行时快照"]
    C --> D["临时事实清除<br/>当前步骤/持物状态/临时约束"]
    D --> E["长期审计记录保留<br/>执行摘要/关键事实结果"]
    E --> F["后续任务启动"]
    F --> G["生成新任务期快照<br/>不继承前一任务<br/>的临时事实"]
    G --> H["基于当前空间语义<br/>和传感器数据<br/>建立新的当前事实"]

    style A fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style B fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style C fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style D fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style E fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style F fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style G fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style H fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
```

## 图 12 可选交互层、端侧概念内化与云端候选服务边界图

```mermaid
%%{init: {'flowchart': {'htmlLabels': true}, 'theme': 'base', 'themeVariables': { 'primaryColor':'#ffffff', 'primaryBorderColor':'#000000', 'background':'#ffffff', 'mainBkg':'#ffffff', 'clusterBkg':'#ffffff', 'clusterBorder':'#000000', 'lineColor':'#000000', 'tertiaryColor':'#ffffff', 'fontSize':'16px'}}}%%
graph TD
    A["交互输入"] --> B["交互层<br/>结构化输入解析<br/>状态外化输出"]
    B --> C{"是否需要<br/>端侧概念内化"}
    C -->|是| D["端侧概念内化<br/>输出候选概念<br/>候选步骤"]
    C -->|否| E{"是否需要<br/>云端候选服务"}
    D --> E
    E -->|是| F["云端候选服务<br/>输出候选链路<br/>或澄清问题"]
    E -->|否| G["直接进入<br/>状态优先仲裁"]
    F --> G
    D --> G
    G --> H["任务期快照读取<br/>输入分流<br/>仲裁判定"]
    H --> I["候选内容不直接<br/>取得执行权<br/>必须回到仲裁"]

    style A fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style B fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style C fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style D fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style E fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style F fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style G fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style H fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style I fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
```
