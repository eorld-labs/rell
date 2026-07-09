# P016 附图 Mermaid 稿

> 本文档用于集中存放说明书附图的 Mermaid 绘图稿。附图采用黑白线框风格，便于后续导出为正式附图或交由代理人重绘。

## 图 1 物理动作执行与经验复用方法的总体流程图

```mermaid
%%{init: {'flowchart': {'htmlLabels': true}, 'theme': 'base', 'themeVariables': { 'primaryColor':'#ffffff', 'primaryBorderColor':'#000000', 'background':'#ffffff', 'mainBkg':'#ffffff', 'clusterBkg':'#ffffff', 'clusterBorder':'#000000', 'lineColor':'#000000', 'tertiaryColor':'#ffffff', 'fontSize':'16px'}}}%%
graph TD
    A["待执行物理动作"] --> B["S101 获取物理动作的<br/>过程模板"]
    B --> C["S102 获取当前执行环境下的<br/>偶然绑定数据"]
    C --> D["S103 填充参数槽<br/>生成物理动作实例"]
    D --> E["S104 执行物理动作实例<br/>并基于连续状态变量触发阶段跃迁"]
    E --> F["S105 从因果事实声明中<br/>确定目标因果事实"]
    F --> G["通过至少两个独立观测通道<br/>生成成立判断"]
    G --> H["确定目标因果事实的<br/>最终成立状态"]
    H --> I["S106 基于最终成立状态<br/>控制阶段推进、恢复执行<br/>或后续物理动作触发"]
    I --> J["执行记录及最终成立状态<br/>回写经验库"]
    J -.可选反馈.-> B

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

## 图 2 过程模板、偶然绑定数据和物理动作实例之间的数据结构关系图

```mermaid
%%{init: {'flowchart': {'htmlLabels': true}, 'theme': 'base', 'themeVariables': { 'primaryColor':'#ffffff', 'primaryBorderColor':'#000000', 'background':'#ffffff', 'mainBkg':'#ffffff', 'clusterBkg':'#ffffff', 'clusterBorder':'#000000', 'lineColor':'#000000', 'tertiaryColor':'#ffffff', 'fontSize':'16px'}}}%%
graph TD
    A["过程模板"] --> A1["阶段序列"]
    A --> A2["连续状态变量类型"]
    A --> A3["跃迁条件逻辑结构"]
    A --> A4["参数槽"]
    A --> A5["因果事实声明引用"]

    B["偶然绑定数据"] --> B1["传感器映射"]
    B --> B2["阈值绑定"]
    B --> B3["对象绑定"]
    B --> B4["执行器资源映射"]
    B --> B5["确认窗口映射"]

    A4 --> C["填充参数槽"]
    B1 --> C
    B2 --> C
    B3 --> C
    C --> D["物理动作实例"]
    D --> D1["绑定后的传感器"]
    D --> D2["绑定后的阈值"]
    D --> D3["绑定后的对象"]
    D --> D4["可执行阶段跃迁条件"]

    style A fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style A1 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style A2 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style A3 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style A4 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style A5 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style B fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style B1 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style B2 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style B3 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style B4 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style B5 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style C fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style D fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style D1 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style D2 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style D3 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style D4 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
```

## 图 3 必然层、因果层和偶然层的三层组织结构图

```mermaid
%%{init: {'flowchart': {'htmlLabels': true}, 'theme': 'base', 'themeVariables': { 'primaryColor':'#ffffff', 'primaryBorderColor':'#000000', 'background':'#ffffff', 'mainBkg':'#ffffff', 'clusterBkg':'#ffffff', 'clusterBorder':'#000000', 'lineColor':'#000000', 'tertiaryColor':'#ffffff', 'fontSize':'16px'}}}%%
graph TD
    A["必然层"] --> A1["物理动作不变过程结构"]
    A --> A2["过程模板"]
    A --> A3["阶段序列、连续状态变量类型<br/>跃迁条件逻辑结构、参数槽"]

    B["因果层"] --> B1["因果事实声明"]
    B --> B2["因果前提事实"]
    B --> B3["因果产出事实"]
    B --> B4["因果销毁事实"]

    C["偶然层"] --> C1["当前执行环境下的<br/>具体绑定数据"]
    C --> C2["传感器映射"]
    C --> C3["阈值绑定"]
    C --> C4["对象绑定"]
    C --> C5["确认窗口映射"]

    A --> D["物理动作实例生成"]
    B --> D
    C --> D
    D --> E["真实物理动作执行闭环"]

    style A fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style A1 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style A2 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style A3 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style B fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style B1 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style B2 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style B3 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style B4 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style C fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style C1 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style C2 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style C3 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style C4 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style C5 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style D fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style E fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
```

## 图 4 阶段跃迁执行流程图

```mermaid
%%{init: {'flowchart': {'htmlLabels': true}, 'theme': 'base', 'themeVariables': { 'primaryColor':'#ffffff', 'primaryBorderColor':'#000000', 'background':'#ffffff', 'mainBkg':'#ffffff', 'clusterBkg':'#ffffff', 'clusterBorder':'#000000', 'lineColor':'#000000', 'tertiaryColor':'#ffffff', 'fontSize':'16px'}}}%%
graph TD
    A["进入当前执行阶段"] --> B["读取当前阶段关联的<br/>连续状态变量类型"]
    B --> C["根据传感器映射<br/>获取对应传感器数据"]
    C --> D["生成连续状态变量观测值"]
    D --> E["读取阈值绑定对应的<br/>具体阈值或判别边界"]
    E --> F["将观测值代入<br/>跃迁条件逻辑结构"]
    F --> G{"跃迁条件是否满足"}
    G -->|是| H{"确认条件是否满足<br/>持续时长、次数或积分"}
    H -->|是| I["触发阶段跃迁<br/>进入下一阶段"]
    H -->|否| J["继续执行或等待确认"]
    G -->|否| K{"是否满足<br/>失败检测条件"}
    K -->|否| L["继续执行、等待<br/>或调整动作"]
    K -->|是| M["触发失败检测"]
    M --> N["读取失败时刻的<br/>连续状态变量观测值"]
    N --> O["确定恢复执行的<br/>入口阶段"]
    J --> C
    L --> C
    I --> P["更新阶段状态"]

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
    style P fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
```

## 图 5 目标因果事实最终成立状态确定流程图

```mermaid
%%{init: {'flowchart': {'htmlLabels': true}, 'theme': 'base', 'themeVariables': { 'primaryColor':'#ffffff', 'primaryBorderColor':'#000000', 'background':'#ffffff', 'mainBkg':'#ffffff', 'clusterBkg':'#ffffff', 'clusterBorder':'#000000', 'lineColor':'#000000', 'tertiaryColor':'#ffffff', 'fontSize':'16px'}}}%%
graph TD
    A["过程模板关联的<br/>因果事实声明"] --> B["确定目标因果事实"]
    B --> C["第一独立观测通道<br/>生成成立判断"]
    B --> D["第二独立观测通道<br/>生成成立判断"]
    C --> E["判断结果汇集"]
    D --> E
    E --> F{"成立判断是否一致"}
    F -->|一致| G["根据一致判断确定<br/>最终成立状态"]
    F -->|不一致| H["根据预设仲裁策略确定<br/>最终成立状态"]
    H --> I["成立、不成立、未知、<br/>待重新观测、冲突需仲裁<br/>或需恢复执行"]
    G --> I
    I --> J["输出目标因果事实的<br/>最终成立状态"]

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

## 图 6 执行闭环与最终成立状态回流示意图

```mermaid
%%{init: {'flowchart': {'htmlLabels': true}, 'theme': 'base', 'themeVariables': { 'primaryColor':'#ffffff', 'primaryBorderColor':'#000000', 'background':'#ffffff', 'mainBkg':'#ffffff', 'clusterBkg':'#ffffff', 'clusterBorder':'#000000', 'lineColor':'#000000', 'tertiaryColor':'#ffffff', 'fontSize':'16px'}}}%%
graph TD
    A["过程模板"] --> B["参数槽"]
    B --> C["偶然绑定数据"]
    C --> D["物理动作实例"]
    D --> E["连续状态变量观测值"]
    E --> F["阶段跃迁判断"]
    F --> G["目标因果事实"]
    G --> H["第一独立观测通道"]
    G --> I["第二独立观测通道"]
    H --> J["双通道验真"]
    I --> J
    J --> K["最终成立状态"]
    K --> L["阶段推进"]
    K --> M["恢复执行"]
    K --> N["后续物理动作触发"]
    K --> O["当前世界状态更新"]
    L --> P["执行记录回传"]
    M --> P
    N --> P
    O --> P
    P --> Q["经验库更新"]
    Q --> A

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
    style P fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style Q fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
```

## 图 7 倒水动作过程模板示意图

```mermaid
%%{init: {'flowchart': {'htmlLabels': true}, 'theme': 'base', 'themeVariables': { 'primaryColor':'#ffffff', 'primaryBorderColor':'#000000', 'background':'#ffffff', 'mainBkg':'#ffffff', 'clusterBkg':'#ffffff', 'clusterBorder':'#000000', 'lineColor':'#000000', 'tertiaryColor':'#ffffff', 'fontSize':'16px'}}}%%
graph TD
    A["倒水动作过程模板"] --> B["定位阶段"]
    B --> C["倾斜阶段"]
    C --> D["保持流动阶段"]
    D --> E["回正阶段"]

    F["连续状态变量类型"] --> F1["壶嘴到杯口距离"]
    F --> F2["倾角"]
    F --> F3["流速"]
    F --> F4["液位高度"]

    G["参数槽"] --> G1["距离阈值标识"]
    G --> G2["最小流速阈值标识"]
    G --> G3["目标液位阈值标识"]
    G --> G4["杯对象引用"]
    G --> G5["水壶对象引用"]
    G --> G6["传感器引用"]

    H["因果事实声明"] --> H1["因果前提事实<br/>杯口已对准"]
    H --> H2["因果前提事实<br/>壶中有液体"]
    H --> H3["因果产出事实<br/>杯中液位达到目标高度"]
    H --> H4["因果销毁事实<br/>壶中液量保持原值不再成立"]

    B -.-> F1
    C -.-> F2
    C -.-> F3
    D -.-> F4
    G --> B
    G --> C
    G --> D

    style A fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style B fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style C fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style D fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style E fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style F fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style F1 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style F2 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style F3 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style F4 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style G fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style G1 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style G2 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style G3 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style G4 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style G5 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style G6 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style H fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style H1 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style H2 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style H3 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style H4 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
```

## 图 8 插入或装配动作过程模板示意图

```mermaid
%%{init: {'flowchart': {'htmlLabels': true}, 'theme': 'base', 'themeVariables': { 'primaryColor':'#ffffff', 'primaryBorderColor':'#000000', 'background':'#ffffff', 'mainBkg':'#ffffff', 'clusterBkg':'#ffffff', 'clusterBorder':'#000000', 'lineColor':'#000000', 'tertiaryColor':'#ffffff', 'fontSize':'16px'}}}%%
graph TD
    A["插入或装配动作过程模板"] --> B["对准阶段"]
    B --> C["接触阶段"]
    C --> D["插入阶段"]
    D --> E["到位确认阶段"]

    F["连续状态变量类型"] --> F1["姿态偏差"]
    F --> F2["接触力"]
    F --> F3["位移"]
    F --> F4["阻抗变化"]

    G["参数槽"] --> G1["插头对象引用"]
    G --> G2["插座对象引用"]
    G --> G3["力传感器引用"]
    G --> G4["接触阈值标识"]
    G --> G5["位移阈值标识"]

    H["因果事实声明"] --> H1["因果前提事实<br/>插座已识别"]
    H --> H2["因果前提事实<br/>插头已对准"]
    H --> H3["因果产出事实<br/>插头已到位"]
    H --> H4["因果销毁事实<br/>插头不再位于初始位置"]

    B -.-> F1
    C -.-> F2
    D -.-> F3
    D -.-> F4
    G --> B
    G --> C
    G --> D

    style A fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style B fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style C fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style D fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style E fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style F fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style F1 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style F2 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style F3 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style F4 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style G fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style G1 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style G2 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style G3 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style G4 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style G5 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style H fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style H1 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style H2 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style H3 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style H4 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
```

## 图 9 云端经验库、边缘端和机器人端协同实施示意图

```mermaid
%%{init: {'flowchart': {'htmlLabels': true}, 'theme': 'base', 'themeVariables': { 'primaryColor':'#ffffff', 'primaryBorderColor':'#000000', 'background':'#ffffff', 'mainBkg':'#ffffff', 'clusterBkg':'#ffffff', 'clusterBorder':'#000000', 'lineColor':'#000000', 'tertiaryColor':'#ffffff', 'fontSize':'16px'}}}%%
graph TD
    A["云端经验库"] --> A1["存储过程模板"]
    A --> A2["存储历史执行记录"]
    A --> A3["更新推荐阈值、确认窗口<br/>通道置信度和恢复入口参数"]

    B["边缘端或部署端"] --> B1["识别场景上下文"]
    B --> B2["生成偶然绑定数据"]
    B --> B3["校验传感器、阈值和对象绑定"]

    C["机器人端"] --> C1["接收物理动作实例"]
    C --> C2["执行阶段序列"]
    C --> C3["获取连续状态变量观测值"]
    C --> C4["触发阶段跃迁"]

    D["事实验真模块"] --> D1["接收目标因果事实"]
    D --> D2["独立观测通道判断"]
    D --> D3["输出最终成立状态"]

    A1 --> B2
    B2 --> C1
    C3 --> D2
    D3 --> C4
    D3 --> C2
    C2 --> E["执行记录回传"]
    E --> A2
    E --> A3

    style A fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style A1 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style A2 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style A3 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style B fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style B1 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style B2 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style B3 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style C fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style C1 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style C2 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style C3 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style C4 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style D fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style D1 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style D2 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style D3 fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
    style E fill:#ffffff,stroke:#000000,stroke-width:2px,color:#000000
```
