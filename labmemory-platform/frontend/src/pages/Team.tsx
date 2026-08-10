export default function Team() {
  const members = [
    {
      tag: "产品与可信记忆",
      tagColor: "blue",
      name: "王健俊",
      desc: "负责产品架构、实验主张模型、行动前审计、评测体系、Demo 与路演。具备 AI 应用开发、MCP/Agent 治理、RAG、Benchmark 和失败分析经验。",
      scope: "GitHub：passionworkeer\n证明：蕉内 AI 应用工程、腾讯联合 Benchmark、共享记忆总线",
    },
    {
      tag: "知识工程与 RAG",
      tagColor: "green",
      name: "韩广宁",
      desc: "负责文档与表格解析、术语归一、语义抽取、混合检索、RESTful 服务与容器化部署。熟悉 PaddleOCR、Milvus、Dify、Docker 及 Python/Java/TypeScript。",
      scope: "证明：企业级品牌文件解析、指标质量检测、QC 智能审查；AI³ Growth Journey 第 8 期冠军",
    },
    {
      tag: "Agent 与平台后端",
      tagColor: "purple",
      name: "林俊衡",
      desc: "负责 Agent 编排、任务与权限服务、飞书及实验系统适配、模型部署和平台可靠性。熟悉 FastAPI、Spring Boot、Spring Security、Redis 及模型微调。",
      scope: "GitHub：Linz1248\n研究：Stable Diffusion、GAN 与图像生成相关论文",
    },
  ];

  const deliveryLane = [
    { b: "需求与流程", p: "产品边界、用户角色、试点场景与验收指标", active: true },
    { b: "多源解析", p: "会议、文档、表格与实验记录进入统一对象模型" },
    { b: "检索与校验", p: "结构化过滤、BM25、向量、Rerank 与证据闸门" },
    { b: "Agent 编排", p: "决策编译、复核、审计、任务和结果回流" },
    { b: "后端与权限", p: "FastAPI/Java 服务、Redis、身份与最小权限" },
    { b: "评测与回归", p: "字段准确率、冲突真值、异常演练与影子运行" },
    { b: "部署与演示", p: "Docker、前后端联调、离线 Demo 与企业试点", active: true },
  ];

  return (
    <div>
      <div className="mb-3">
        <h2 className="text-lg font-bold">团队与工程落地</h2>
        <p className="text-sm text-muted">产品判断、知识工程和平台工程形成完整交付链路</p>
      </div>

      <div className="grid grid-cols-3 gap-4 mb-6 max-md:grid-cols-1">
        {members.map((m) => (
          <div className="card" key={m.name}>
            <span className={`tag ${m.tagColor}`}>{m.tag}</span>
            <h3 className="font-bold text-base mt-2">{m.name}</h3>
            <p className="text-muted text-sm leading-relaxed mt-2">{m.desc}</p>
            <div className="mt-3 text-xs rounded-lg p-2.5" style={{ background: "#f7f9fc", lineHeight: 1.65 }}>
              <pre className="whitespace-pre-wrap font-sans">{m.scope}</pre>
            </div>
          </div>
        ))}
      </div>

      <div className="mb-3">
        <h2 className="text-lg font-bold">端到端交付链路</h2>
        <p className="text-sm text-muted">三位成员可独立负责模块，也能共同完成联调</p>
      </div>
      <div className="grid grid-cols-7 gap-2 mb-6 max-md:grid-cols-2">
        {deliveryLane.map((n) => (
          <div
            key={n.b}
            className={`card text-xs ${n.active ? "border-blue-200 bg-blue-soft" : ""}`}
            style={{ padding: 11, minHeight: 88 }}
          >
            <b className="text-sm">{n.b}</b>
            <p className="mt-1.5 leading-relaxed text-muted">{n.p}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-4 max-md:grid-cols-1">
        <div className="card">
          <b>首期 MVP 分工</b>
          <table className="mt-2">
            <thead>
              <tr>
                <th>模块</th>
                <th>牵头</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>产品、知识模型、评测与路演</td>
                <td>王健俊</td>
              </tr>
              <tr>
                <td>解析、RAG、向量库与容器化</td>
                <td>韩广宁</td>
              </tr>
              <tr>
                <td>Agent、Java 后端、权限与模型服务</td>
                <td>林俊衡</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div className="card">
          <b>试点承诺</b>
          <div className="audittrail mt-3">
            <div>模型输出只形成候选，不自动批准关键参数</div>
            <div>原始事实继续保留在 ELN/LIMS/仪器平台</div>
            <div>先影子运行，再受控试点，异常可重试和补偿</div>
            <div>所有收益数字均以试点对照数据验证</div>
          </div>
        </div>
      </div>
    </div>
  );
}
