# 📚 Study Assistant — AI 学习辅导老师

[![Release](https://img.shields.io/github/v/release/2362094903-ops/study-assistant-skills)](https://github.com/2362094903-ops/study-assistant-skills/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Skills-d97757)](https://claude.com/claude-code)

一套用于 [Claude Code](https://claude.com/claude-code) 的系统化学习 Skill 套件。**考研、期末考试、资格证书备考都适用**——上传教材、课件、讲义或任何学习资料，它会像一位严格但耐心的辅导老师一样带你**按章节吃透**：

> 画思维导图 → 按节生成讲义（每个知识点配例题）→ 按目标院校真题风格出题 → 交互试卷即时判分 → 错题本换壳复盘 → 费曼检验验收 → 仪表盘追踪掌握度。**学习进度跨会话保存**，随时"继续学习"接着上次的进度。

*A study-tutor skill suite for Claude Code — works for any exam or course (graduate entrance exams, university finals, certifications): mind maps, section-by-section lecture notes with worked examples, exam-style interactive quizzes, a mistake book, Feynman-technique verification, and a mastery dashboard — all state persisted across sessions. Instructions are written in English for cross-model reliability; all learner-facing output is Simplified Chinese.*

---

## ✨ 亮点

- 🧠 **交互式思维导图**：零依赖单文件 HTML，折叠/缩放/搜索，知识点**按掌握度着色**——学到哪绿到哪
- 📖 **整章讲义**：按节生成，Obsidian Markdown（LaTeX 原生渲染、例题答案折叠、可当 vault）/ 交互 HTML（侧边目录、MathJax 公式、"标记已学"）双格式任选
- ✍️ **真题风格出题**：上传真题或历年试卷（考研真题、期末卷均可）自动分析命题风格（手头没有可联网代找）；交互试卷支持单选/多选/判断/主观题，**做完一题立即显示答案与解析**；纸上手写作答拍照也能批改
- 🔁 **错题闭环**：错题自动入本，复盘时换数字换情境重考，答对才销账；全书模拟卷按"重要度高 × 掌握度低"抽样暴露短板
- 🗣️ **费曼检验**：你讲给"聪明的初学者"听，它追问漏洞、评 1–5 分掌握度、出章节掌握报告
- 📊 **学习仪表盘**：掌握度分布、各章进度、趋势线、薄弱点清单；同时生成 30 行模型摘要——**新会话恢复全部学习状态只需读这 30 行**，几乎不占上下文
- ♻️ **题库复用**：出过的题和讲义例题自动入库，再次出题先查库改编，大幅节省 token
- 👁️ **识图自适应**：模型有视觉能力就直接看；没有则调用**你自己配置的**视觉模型 API（OpenAI 兼容 / Anthropic 格式均可），扫描版教材、试卷照片、手写答案都能处理

## 🏗️ 架构

```mermaid
flowchart LR
    U[用户] --> A[study-assistant<br/>主控编排 + 学习档案]
    A --> M[study-mindmap<br/>思维导图]
    A --> T[study-teach<br/>讲义 + 答疑]
    A --> Q[study-quiz<br/>出题 · 批改 · 错题本]
    A --> F[study-feynman<br/>费曼检验]
    A --> I[study-img<br/>识图]
    M & T & Q & F -.读写.-> S[(学习工作区<br/>knowledge.json · progress.json<br/>history.jsonl · question-bank.json)]
```

| Skill | 职责 |
|---|---|
| `study-assistant` | **主控**：建档、编排全流程、节奏控制、跨会话续学（只读 30 行摘要） |
| `study-mindmap` | 交互思维导图，掌握度着色，随学习进度刷新 |
| `study-teach` | 按节讲义（七要素：考情/直观/严谨/例题/易错/记忆/关联）+ 对话答疑重讲 |
| `study-quiz` | 真题风格分析（可联网找真题）、交互试卷、批改、错题本、模拟卷、题库 |
| `study-feynman` | 费曼检验、掌握度评分、章节掌握报告 |
| `study-img` | 原生视觉优先；无视觉则调用用户自配 API（OCR / 图表描述 / 手写转录） |

所有产物（导图/试卷/讲义/仪表盘）由**模型写结构化 JSON、打包脚本渲染**——换什么模型驱动，页面长一个样；状态文件有校验脚本兜底。

## 🚀 安装

### Claude Code（命令行 / 桌面版 / IDE 插件）

```bash
git clone https://github.com/2362094903-ops/study-assistant-skills.git
cp -r study-assistant-skills/study-* ~/.claude/skills/
pip3 install pymupdf   # 处理 PDF 教材需要；其余功能零依赖
```

### Claude 桌面应用（claude.ai App）

从 [Releases](https://github.com/2362094903-ops/study-assistant-skills/releases) 下载 6 个 `.skill` 文件，在 **设置 → Capabilities → Skills** 中上传。注意：沙箱环境下跨会话续学等依赖本地文件的能力会受限，完整体验请用 Claude Code。

## 📖 快速开始

```
开始学习 ~/Documents/课程/微观经济学.pdf 第三章
```

其余常用说法：

| 你说 | 它做 |
|---|---|
| `继续学习` | 读 30 行摘要恢复状态，汇报进度，接着学 |
| `生成下一节讲义` | 按节产出讲义（Obsidian / HTML） |
| `没听懂 XXX，换个讲法` | 换比喻换例子重讲（不复读讲义） |
| `这是真题/历年试卷 <文件>` | 分析命题风格，之后出题都模仿它 |
| `出题考我` / `来套模拟卷` | 打开交互试卷 → 做完导出作答记录贴回 → 批改+错题本 |
| 拍照上传手写答案 | OCR 忠实转录（不纠错）→ 你确认 → 批改 |
| `用费曼学习法检验我` | 你讲、它追问、评分、出报告 |
| `复盘错题本` | 错题换壳重考，答对销账 |
| `打开仪表盘` | 掌握度分布/趋势/薄弱点一页看全 |

学习数据存在教材文件旁的 `<教材名>-study/` 文件夹：

```
<教材名>-study/
├── knowledge.json      # 知识点树（重要度/状态/掌握度）
├── progress.json       # 进度与日志
├── history.jsonl       # 掌握度变更流水（驱动趋势图）
├── digest.md           # 30 行模型摘要（续学只读它）
├── dashboard.html      # 学习仪表盘
├── question-bank.json  # 题库
├── mindmaps/ lessons/ quizzes/ reports/
├── exam-style.md       # 真题风格档案
└── mistakes.md         # 错题本
```

删除该文件夹 = 重置进度；备份它 = 备份全部学习记录。把它用 Obsidian 作为 vault 打开，讲义公式即原生渲染。

## 🔧 识图配置（仅当你的模型没有视觉能力时）

模型本身能看图（如 Claude Sonnet/Opus）则零配置。否则首次识图时会引导你配置，写入 `~/.config/study-img/config.json`：

```json
{
  "provider": "openai",
  "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
  "api_key": "<你的密钥>",
  "model": "qwen3.5-flash"
}
```

- `openai`：任何 OpenAI 兼容接口（DashScope / 智谱 / Moonshot / SiliconFlow / OpenRouter / OpenAI…）
- `anthropic`：Anthropic Messages API（`base_url` 可省略）
- 也支持环境变量 `STUDY_IMG_*`；验证：`python3 ~/.claude/skills/study-img/scripts/recognize.py --show-config`

密钥只存你本机，不会出现在仓库或学习档案中。

## ❓ FAQ

**对模型有什么要求？** 任何能跑 Claude Code 的模型都行。指令为英文编写以提高跨模型遵循度，输出强制简体中文；产物由脚本渲染保证一致性。模型无视觉能力时识图走外部 API。

**公式怎么渲染？** 讲义用 LaTeX（Obsidian 原生渲染；HTML 版经 MathJax CDN，离线退化为源码显示）；思维导图和试卷为保持零依赖离线可用，公式用 Unicode 写法（MU₁/P₁ = λ）。

**我的教材和学习数据会上传吗？** 不会。所有档案都是你本机的纯文本/HTML 文件。唯一的外部调用是：①无视觉模型时的识图 API（你自己的）；②你主动要求联网找真题时的网页检索。

**多选题怎么计分？** 默认按考研惯例"错选漏选均不得分"，出题时可设 `partial: true` 改为漏选无错选得半分。

**为什么讲义按节生成而不是一次出整章？** 单次生成内容越长，后半段质量越容易下滑。按节生成质量稳定，读完一节再要下一节即可。

## 📄 License

[MIT](LICENSE)
