# P017 附图 Mermaid 稿

> 本文档用于集中存放说明书附图的 Mermaid 绘图稿。附图采用黑白线框风格，便于后续导出为正式附图或交由代理人重绘。图中文字仅用于说明数据、模块和步骤之间的关系，不限定本发明保护范围。

## 图 1 跨空间跨本体真实经验迁移执行方法总体流程图

```mermaid
%%{init: {'flowchart': {'htmlLabels': true}, 'theme': 'base', 'themeVariables': { 'primaryColor':'#ffffff', 'primaryBorderColor':'#000000', 'background':'#ffffff', 'mainBkg':'#ffffff', 'clusterBkg':'#ffffff', 'clusterBorder':'#000000', 'lineColor':'#000000', 'tertiaryColor':'#ffffff', 'fontSize':'16px'}}}%%
graph TD
    A["待迁移经验记录"] --> B["S101 获取经验记录<br/>目标因果事实、过程链或模板引用、经验不变量契约"]
    B --> C["S102 获取当前迁移上下文<br/>当前空间语义数据、本体能力画像、任务意图"]
    C --> D["S103 生成任务期运行时世界状态快照<br/>用于当前任务事实对齐和工作记忆"]
    D --> E["S104 跨空间跨本体适配<br/>生成绑定候选以及执行可行性结果"]
    E --> F{"执行可行性结果<br/>是否表示可执行"}
    F -->|是| G["S105 调用执行闭环<br/>执行通过适配判断的经验步骤"]
    G --> H["S106 接收事实回传<br/>依据因果产出事实和因果销毁事实更新快照"]
    H --> I["S107 任务结束<br/>删除或释放任务期快照"]
    I --> J["写入审计记录或经验记录<br/>关键事实结果、轨迹摘要、失败恢复、人工确认"]
    F -->|否| K["输出不可执行或部分不可执行结果<br/>人工确认、替代经验、补充教学、降级执行或终止执行"]
    K --> I

    classDef bw fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000;
    class A,B,C,D,E,F,G,H,I,J,K bw;
```

## 图 2 经验记录、经验不变量契约、当前空间语义数据、本体能力画像和任务期运行时世界状态快照之间的数据关系图

```mermaid
%%{init: {'flowchart': {'htmlLabels': true}, 'theme': 'base', 'themeVariables': { 'primaryColor':'#ffffff', 'primaryBorderColor':'#000000', 'background':'#ffffff', 'mainBkg':'#ffffff', 'clusterBkg':'#ffffff', 'clusterBorder':'#000000', 'lineColor':'#000000', 'tertiaryColor':'#ffffff', 'fontSize':'16px'}}}%%
graph TD
    A["经验记录"] --> A1["目标因果事实"]
    A --> A2["过程链或过程模板引用"]
    A --> A3["经验不变量契约"]
    A -.可选审计.-> A4["可选审计轨迹摘要或历史证据引用"]

    B["当前迁移上下文"] --> B1["当前空间语义数据<br/>语义区域、对象、对象关系、可供性、导航关系"]
    B --> B2["本体能力画像<br/>执行体类型、支持动作、可达范围、传感器能力"]
    B --> B3["任务意图"]

    C["任务期运行时世界状态快照"] --> C1["执行体所在语义区域"]
    C --> C2["执行体持有物"]
    C --> C3["已成立事实、待验证事实、冲突事实"]
    C --> C4["当前过程节点或当前绑定候选"]

    A1 --> D["迁移适配判断"]
    A2 --> D
    A3 --> D
    B1 --> D
    B2 --> D
    B3 --> C
    C --> D
    D --> E["绑定候选以及执行可行性结果"]
    E --> F["执行闭环调用或不可执行处理"]

    classDef bw fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000;
    class A,A1,A2,A3,A4,B,B1,B2,B3,C,C1,C2,C3,C4,D,E,F bw;
```

## 图 3 经验不变量契约的结构示意图

```mermaid
%%{init: {'flowchart': {'htmlLabels': true}, 'theme': 'base', 'themeVariables': { 'primaryColor':'#ffffff', 'primaryBorderColor':'#000000', 'background':'#ffffff', 'mainBkg':'#ffffff', 'clusterBkg':'#ffffff', 'clusterBorder':'#000000', 'lineColor':'#000000', 'tertiaryColor':'#ffffff', 'fontSize':'16px'}}}%%
graph TD
    A["经验不变量契约"] --> B["拓扑关系不变量"]
    A --> C["试探方向与物理约束不变量"]
    A --> D["事实终止条件不变量"]
    A --> E["不可迁移内容排除标记"]

    B --> B1["执行体到达语义区域"]
    B --> B2["末端执行器持有对象"]
    B --> B3["对象开口与目标对象对齐"]
    B --> B4["工具作用部位与目标作用部位满足相对关系"]

    C --> C1["动作方向"]
    C --> C2["允许运动边界或最大运动限制"]
    C --> C3["安全、负载、接触力或姿态限制"]
    C --> C4["本体约束"]

    D --> D1["目标因果事实成立"]
    D --> D2["连续状态变量满足阈值"]
    D --> D3["独立观测通道判断一致"]
    D --> D4["人工确认或执行闭环最终成立状态"]

    E --> E1["不作为迁移必要内容<br/>绝对坐标"]
    E --> E2["不作为迁移必要内容<br/>机器人专用关节角"]
    E --> E3["不作为迁移必要内容<br/>固定执行时长"]
    E --> E4["不作为迁移必要内容<br/>单一本体轨迹或固定绑定值"]

    classDef bw fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000;
    class A,B,C,D,E,B1,B2,B3,B4,C1,C2,C3,C4,D1,D2,D3,D4,E1,E2,E3,E4 bw;
```

## 图 4 基于经验不变量契约和当前迁移上下文生成绑定候选以及执行可行性结果的流程图

```mermaid
%%{init: {'flowchart': {'htmlLabels': true}, 'theme': 'base', 'themeVariables': { 'primaryColor':'#ffffff', 'primaryBorderColor':'#000000', 'background':'#ffffff', 'mainBkg':'#ffffff', 'clusterBkg':'#ffffff', 'clusterBorder':'#000000', 'lineColor':'#000000', 'tertiaryColor':'#ffffff', 'fontSize':'16px'}}}%%
graph TD
    A["输入经验不变量契约"] --> B["解析拓扑关系不变量"]
    A --> C["解析试探方向与物理约束不变量"]
    A --> D["解析事实终止条件不变量"]

    E["当前空间语义数据"] --> F["空间绑定匹配"]
    B --> F
    F --> F1["对象、语义区域、对象关系<br/>空间绑定候选"]

    G["本体能力画像"] --> H["能力匹配"]
    C --> H
    H --> H1["支持动作、可达范围、传感器、力控、安全限制<br/>能力匹配结果"]

    I["任务期运行时世界状态快照"] --> J["事实状态匹配"]
    D --> J
    J --> J1["已成立事实、待验证事实、冲突事实<br/>终止条件或传感器可验证性"]

    F1 --> K["综合适配决策"]
    H1 --> K
    J1 --> K
    K --> L["生成绑定候选"]
    K --> M["生成执行可行性结果"]
    M --> N{"可执行、部分不可执行<br/>或不可执行"}
    N -->|可执行| O["允许下发执行闭环"]
    N -->|部分不可执行或不可执行| P["输出原因、人工确认、替代经验<br/>补充教学、降级执行或终止执行"]

    classDef bw fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000;
    class A,B,C,D,E,F,F1,G,H,H1,I,J,J1,K,L,M,N,O,P bw;
```

## 图 5 执行闭环返回因果产出事实和因果销毁事实并更新任务期运行时世界状态快照的示意图

```mermaid
%%{init: {'flowchart': {'htmlLabels': true}, 'theme': 'base', 'themeVariables': { 'primaryColor':'#ffffff', 'primaryBorderColor':'#000000', 'background':'#ffffff', 'mainBkg':'#ffffff', 'clusterBkg':'#ffffff', 'clusterBorder':'#000000', 'lineColor':'#000000', 'tertiaryColor':'#ffffff', 'fontSize':'16px'}}}%%
graph TD
    A["通过适配可行性判断的经验步骤"] --> B["执行调度单元"]
    B --> C["执行闭环<br/>过程模板执行器、ROS 控制器、SDK、仿真执行器等"]
    C --> D["执行闭环返回状态"]
    D --> D1["事实成立状态"]
    D --> D2["事实不成立状态"]
    D --> D3["失败、冲突、恢复或人工确认状态"]
    D --> D4["传感器、控制器或执行模块返回结果"]

    D1 --> E["事实回传单元"]
    D2 --> E
    D3 --> E
    D4 --> E
    E --> F["转换为结构化事实"]
    F --> F1["因果产出事实"]
    F --> F2["因果销毁事实"]
    F --> F3["待验证事实或冲突事实"]

    F1 --> G["写入任务期运行时世界状态快照"]
    F2 --> G
    F3 --> G
    G --> H["更新已成立事实集合<br/>待验证事实集合<br/>冲突事实集合"]
    H --> I["后续经验步骤适配判断"]

    classDef bw fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000;
    class A,B,C,D,D1,D2,D3,D4,E,F,F1,F2,F3,G,H,I bw;
```

## 图 6 任务期运行时世界状态快照释放及审计记录保留的示意图

```mermaid
%%{init: {'flowchart': {'htmlLabels': true}, 'theme': 'base', 'themeVariables': { 'primaryColor':'#ffffff', 'primaryBorderColor':'#000000', 'background':'#ffffff', 'mainBkg':'#ffffff', 'clusterBkg':'#ffffff', 'clusterBorder':'#000000', 'lineColor':'#000000', 'tertiaryColor':'#ffffff', 'fontSize':'16px'}}}%%
graph TD
    A["任务期运行时世界状态快照"] --> A1["临时事实集合"]
    A --> A2["待验证事实集合"]
    A --> A3["冲突事实集合"]
    A --> A4["当前过程节点和绑定候选"]

    B{"任务结束、取消、超时<br/>人工终止或执行失败"} --> C["触发快照释放"]
    A --> B
    C --> C1["物理删除"]
    C --> C2["逻辑失效"]
    C --> C3["任务标识解绑"]
    C --> C4["停止作为后续任务适配依据"]

    C --> D["生成释放状态或释放令牌"]
    D --> E["审计记录或经验记录"]
    E --> E1["关键事实成立结果"]
    E --> E2["执行轨迹摘要"]
    E --> E3["失败恢复记录"]
    E --> E4["人工确认记录"]
    E --> E5["release_token 或 release_status"]

    C4 --> F["后续任务重新获取当前事实<br/>防止任务期状态污染"]

    classDef bw fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000;
    class A,A1,A2,A3,A4,B,C,C1,C2,C3,C4,D,E,E1,E2,E3,E4,E5,F bw;
```

## 图 7 迁移适配控制器的系统结构和内部数据流示意图

```mermaid
%%{init: {'flowchart': {'htmlLabels': true}, 'theme': 'base', 'themeVariables': { 'primaryColor':'#ffffff', 'primaryBorderColor':'#000000', 'background':'#ffffff', 'mainBkg':'#ffffff', 'clusterBkg':'#ffffff', 'clusterBorder':'#000000', 'lineColor':'#000000', 'tertiaryColor':'#ffffff', 'fontSize':'16px'}}}%%
graph TD
    A["外部输入"] --> A1["经验记录"]
    A --> A2["当前空间语义数据"]
    A --> A3["本体能力画像"]
    A --> A4["任务意图"]

    A1 --> B["接口单元"]
    A2 --> B
    A3 --> B
    A4 --> B
    B --> C["契约解析单元"]
    C --> D["空间绑定单元"]
    C --> E["能力匹配单元"]
    B --> F["状态管理单元"]

    D --> G["适配决策单元"]
    E --> G
    F --> G
    G --> G1["绑定候选"]
    G --> G2["执行可行性结果"]
    G --> G3["不可执行原因 / 人工确认 / 替代经验<br/>补充教学 / 降级执行 / 终止执行"]
    G1 --> H["执行调度单元"]
    G2 --> H
    G3 --> K
    H --> I["执行闭环接口"]
    I --> J["事实回传单元"]
    J --> J1["因果产出事实"]
    J --> J2["因果销毁事实"]
    J --> J3["冲突事实或待验证事实"]
    J1 --> F
    J2 --> F
    J3 --> F
    F --> K["审计释放单元"]
    K --> K1["审计记录"]
    K --> K2["释放令牌或释放状态"]

    classDef bw fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000;
    class A,A1,A2,A3,A4,B,C,D,E,F,G,G1,G2,G3,H,I,J,J1,J2,J3,K,K1,K2 bw;
```

## 图 8 云端经验库、边缘迁移适配器和机器人端执行闭环协同实施示意图

```mermaid
%%{init: {'flowchart': {'htmlLabels': true}, 'theme': 'base', 'themeVariables': { 'primaryColor':'#ffffff', 'primaryBorderColor':'#000000', 'background':'#ffffff', 'mainBkg':'#ffffff', 'clusterBkg':'#ffffff', 'clusterBorder':'#000000', 'lineColor':'#000000', 'tertiaryColor':'#ffffff', 'fontSize':'16px'}}}%%
graph TD
    A["云端经验库"] --> A1["经验记录"]
    A --> A2["经验不变量契约"]
    A --> A3["历史执行记录或审计摘要"]

    B["空间语义服务"] --> B1["当前空间语义数据"]
    C["机器人 SDK 或能力服务"] --> C1["本体能力画像"]

    A1 --> D["迁移适配控制器<br/>云端、边缘或协同部署"]
    A2 --> D
    B1 --> D
    C1 --> D
    D --> D1["任务期运行时世界状态快照"]
    D --> D2["绑定候选"]
    D --> D3["执行可行性结果"]

    D2 --> E["机器人端执行闭环"]
    D3 --> E
    E --> F["事实回传状态"]
    F --> D
    D --> G["云端审计系统"]
    G --> G1["migration_task_id"]
    G --> G2["binding_candidate_id"]
    G --> G3["execution_callback_id"]
    G --> G4["release_token"]

    D -.逻辑控制主体.-> H["同一迁移任务标识下<br/>编排、鉴权、状态绑定和审计关联"]

    classDef bw fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000;
    class A,A1,A2,A3,B,B1,C,C1,D,D1,D2,D3,E,F,G,G1,G2,G3,G4,H bw;
```

## 图 9 不可执行或部分不可执行结果触发人工确认、替代经验搜索或补充教学的流程图

```mermaid
%%{init: {'flowchart': {'htmlLabels': true}, 'theme': 'base', 'themeVariables': { 'primaryColor':'#ffffff', 'primaryBorderColor':'#000000', 'background':'#ffffff', 'mainBkg':'#ffffff', 'clusterBkg':'#ffffff', 'clusterBorder':'#000000', 'lineColor':'#000000', 'tertiaryColor':'#ffffff', 'fontSize':'16px'}}}%%
graph TD
    A["生成执行可行性结果"] --> B{"结果类型"}
    B -->|可执行| C["调用执行闭环"]
    B -->|不可执行| D["输出不可执行原因"]
    B -->|部分不可执行| E["区分可执行部分和不可执行部分"]
    B -->|需降级执行| F["对可执行部分进行降级执行"]
    B -->|需人工确认| G["请求人工确认"]
    B -->|需补充教学| H["触发补充教学"]
    B -->|需搜索替代经验| I["搜索替代经验"]

    D --> J["记录经验缺口"]
    E --> F
    F --> J
    G --> J
    H --> J
    I --> J
    J --> J1["缺失对象"]
    J --> J2["缺失能力或传感器"]
    J --> J3["缺失事实前提"]
    J --> J4["可执行步骤集合和不可执行步骤集合"]
    J --> J5["替代经验候选或教学入口"]
    J --> K["写入任务期快照或审计记录"]
    K --> L{"是否获得确认、替代经验<br/>或补充教学结果"}
    L -->|是| M["重新适配"]
    L -->|否| N["终止执行或保持不可执行状态"]
    M --> A

    classDef bw fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000;
    class A,B,C,D,E,F,G,H,I,J,J1,J2,J3,J4,J5,K,L,M,N bw;
```

## 图 10 目标因果事实反推前提链的可选实施示意图

```mermaid
%%{init: {'flowchart': {'htmlLabels': true}, 'theme': 'base', 'themeVariables': { 'primaryColor':'#ffffff', 'primaryBorderColor':'#000000', 'background':'#ffffff', 'mainBkg':'#ffffff', 'clusterBkg':'#ffffff', 'clusterBorder':'#000000', 'lineColor':'#000000', 'tertiaryColor':'#ffffff', 'fontSize':'16px'}}}%%
graph TD
    A["目标因果事实"] --> B["读取任务期运行时世界状态快照"]
    C["过程事实注册表"] --> D["记录过程步骤<br/>产出事实、销毁事实、必要前提事实"]
    D --> E["判断目标事实的必要前提事实"]
    B --> E
    E --> F{"必要前提事实<br/>是否已成立"}
    F -->|已成立| G["形成可适配候选过程链"]
    F -->|缺失| H["查询能够产出缺失前提事实的<br/>经验步骤或过程模板"]
    H --> I{"查询结果<br/>是否仍有缺失前提"}
    I -->|有| H
    I -->|无| G
    H -->|不存在可用步骤| J["输出不可执行结果<br/>或补充教学入口"]
    G --> K["对候选过程链中各经验步骤<br/>执行跨空间跨本体适配判断"]
    K --> L["输出可执行候选过程链<br/>部分不可执行候选过程链<br/>或不可执行结果"]

    classDef bw fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000;
    class A,B,C,D,E,F,G,H,I,J,K,L bw;
```

## 图 11 显式空间路线保真与因果校验的可选实施示意图

```mermaid
%%{init: {'flowchart': {'htmlLabels': true}, 'theme': 'base', 'themeVariables': { 'primaryColor':'#ffffff', 'primaryBorderColor':'#000000', 'background':'#ffffff', 'mainBkg':'#ffffff', 'clusterBkg':'#ffffff', 'clusterBorder':'#000000', 'lineColor':'#000000', 'tertiaryColor':'#ffffff', 'fontSize':'16px'}}}%%
graph TD
    A["用户显式教入空间路线"] --> B["解析路线"]
    B --> B1["语义区域序列"]
    B --> B2["对象操作序列"]
    B --> B3["过程步骤序列"]
    B --> C["保留用户显式指定的空间顺序"]

    D["目标因果事实"] --> E["查询过程事实注册表"]
    E --> E1["必要前提事实"]
    E --> E2["过程事实"]
    C --> F["因果覆盖校验"]
    E1 --> F
    E2 --> F
    F --> G{"路线是否覆盖<br/>必要前提事实和目标因果事实"}
    G -->|覆盖| H["转化为经验记录或经验记录候选"]
    G -->|未覆盖| I["输出缺失事实"]
    I --> J["补齐候选步骤、请求人工确认<br/>或输出不可执行结果"]
    H --> K["进入经验迁移执行主链<br/>适配、执行、事实回传和快照释放"]
    J --> K

    classDef bw fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000;
    class A,B,B1,B2,B3,C,D,E,E1,E2,F,G,H,I,J,K bw;
```

## 图 12 执行闭环开放接口的可选实施示意图

```mermaid
%%{init: {'flowchart': {'htmlLabels': true}, 'theme': 'base', 'themeVariables': { 'primaryColor':'#ffffff', 'primaryBorderColor':'#000000', 'background':'#ffffff', 'mainBkg':'#ffffff', 'clusterBkg':'#ffffff', 'clusterBorder':'#000000', 'lineColor':'#000000', 'tertiaryColor':'#ffffff', 'fontSize':'16px'}}}%%
graph TD
    A["迁移适配控制器"] --> B["生成执行闭环调用载荷"]
    B --> B1["经验步骤"]
    B --> B2["绑定候选"]
    B --> B3["执行约束"]
    B --> B4["目标因果事实"]
    B --> B5["任务期快照标识"]

    B --> C["开放执行闭环接口"]
    C --> C1["过程模板执行器"]
    C --> C2["机器人操作系统控制器"]
    C --> C3["机器人 SDK"]
    C --> C4["仿真执行器"]
    C --> C5["数字执行体或软件自动执行体"]
    C --> C6["VLA 动作策略层或带有结构化状态返回的人工远程操作系统"]

    C1 --> D["执行返回结果"]
    C2 --> D
    C3 --> D
    C4 --> D
    C5 --> D
    C6 --> D
    D --> D1["事实成立或不成立状态"]
    D --> D2["失败、冲突、恢复或人工确认状态"]
    D --> D3["传感器、力矩、关节、工具调用或人工确认结果"]
    D --> E["事实回传单元"]
    E --> F["因果产出事实、因果销毁事实<br/>待验证事实或冲突事实"]
    F --> G["更新任务期运行时世界状态快照"]

    classDef bw fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000;
    class A,B,B1,B2,B3,B4,B5,C,C1,C2,C3,C4,C5,C6,D,D1,D2,D3,E,F,G bw;
```

## 图 13 运行时冲突处理与重新适配的可选实施示意图

```mermaid
%%{init: {'flowchart': {'htmlLabels': true}, 'theme': 'base', 'themeVariables': { 'primaryColor':'#ffffff', 'primaryBorderColor':'#000000', 'background':'#ffffff', 'mainBkg':'#ffffff', 'clusterBkg':'#ffffff', 'clusterBorder':'#000000', 'lineColor':'#000000', 'tertiaryColor':'#ffffff', 'fontSize':'16px'}}}%%
graph TD
    A["执行过程中监测运行状态"] --> B{"是否出现变化或冲突"}
    B -->|否| C["继续执行当前经验步骤"]
    B -->|是| D["识别冲突类型"]
    D --> D1["空间语义数据与实时观测不一致"]
    D --> D2["本体能力画像与运行时能力检测不一致"]
    D --> D3["执行闭环返回状态与事实终止条件不一致"]
    D --> D4["外部服务返回结果之间不一致"]

    D1 --> E["将冲突事实写入任务期快照"]
    D2 --> E
    D3 --> E
    D4 --> E
    E --> F["基于更新后的任务期快照<br/>重新执行空间绑定、能力匹配或事实匹配"]
    F --> G["重新生成绑定候选以及执行可行性结果"]
    G --> H{"重新适配结果"}
    H -->|可执行| I["继续或恢复执行"]
    H -->|部分不可执行| J["降级执行、替代经验搜索或人工确认"]
    H -->|不可执行| K["终止执行或触发补充教学"]
    I --> L["更新快照并写入审计记录"]
    J --> L
    K --> L

    classDef bw fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000;
    class A,B,C,D,D1,D2,D3,D4,E,F,G,H,I,J,K,L bw;
```

## 图 14 经验不变量契约生成的可选实施示意图

```mermaid
%%{init: {'flowchart': {'htmlLabels': true}, 'theme': 'base', 'themeVariables': { 'primaryColor':'#ffffff', 'primaryBorderColor':'#000000', 'background':'#ffffff', 'mainBkg':'#ffffff', 'clusterBkg':'#ffffff', 'clusterBorder':'#000000', 'lineColor':'#000000', 'tertiaryColor':'#ffffff', 'fontSize':'16px'}}}%%
graph TD
    A["历史执行数据"] --> A1["历史执行日志"]
    A --> A2["人工示教记录"]
    A --> A3["仿真运行记录"]
    A --> A4["低层轨迹、策略代码或模型输出"]
    A --> A5["执行闭环反馈或人工确认记录"]

    A1 --> B["识别目标因果事实、过程步骤<br/>对象关系、动作方向、物理约束和终止条件"]
    A2 --> B
    A3 --> B
    A4 --> B
    A5 --> B

    B --> C["识别可迁移约束"]
    C --> C1["拓扑关系不变量<br/>例如壶嘴与杯口对齐"]
    C --> C2["试探方向与物理约束不变量<br/>例如倾倒方向和最大倾角"]
    C --> C3["事实终止条件不变量<br/>例如水流出现和液位达标"]

    B --> D["识别不可迁移执行细节"]
    D --> D1["固定壶嘴坐标或固定杯口坐标"]
    D --> D2["机器人专用关节角序列"]
    D --> D3["固定执行时长或单一本体轨迹"]
    D --> D4["特定空间绑定值或传感器安装坐标"]

    C1 --> E["生成经验不变量契约"]
    C2 --> E
    C3 --> E
    D1 --> F["保留为审计、回放、训练或故障分析数据<br/>不作为迁移必要内容"]
    D2 --> F
    D3 --> F
    D4 --> F
    E --> G["与目标因果事实、过程链<br/>或过程模板引用关联"]
    G --> H["形成可进入迁移执行主链的经验记录"]

    classDef bw fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000;
    class A,A1,A2,A3,A4,A5,B,C,C1,C2,C3,D,D1,D2,D3,D4,E,F,G,H bw;
```
