# web/ui — 模拟盘看板

`trader/` 模拟盘的只读看板：Vite + React + TypeScript + Tailwind CSS v4。
数据全部来自 `web/api`（同源 `/api/...`），界面术语见仓库根目录 `CONTEXT.md`。

## 开发

```sh
cd web/ui
npm install
npm run dev                                   # 代理 /api -> http://127.0.0.1:8000（先运行 python -m web.api）
VITE_API_PROXY=http://127.0.0.1:8001 npm run dev   # 把 /api 代理到别的地址，比如一个 mock
```

## 构建

```sh
npm run build      # tsc -b && vite build，产物在 dist/，由后端挂在同源 / 下（需要 SPA 回退）
npm run preview
npm run lint       # oxlint
```

## 结构

- `src/api.ts` — 后端契约的 interface 与 `getJson<T>()`、`postJson<T>()`
- `src/hooks.ts` — `useFetch<T>(path, refreshMs?)`
- `src/format.ts` — 数字 / 百分比 / 数量 / UTC 时间格式化
- `src/debate.ts` — 按说话人前缀切分辩论记录
- `src/content/` — 指南章节 `guide.ts`、`?` 提示文案 `help.ts`，以及把 `{{name}}` 占位符换成 `/api/strategy` 常数的 `vars.ts`
- `src/pages/` — 总览 `/`、研判 `/research`、研判详情 `/research/:coin/:date`、信号 `/signals`（仅日内账户）、历史 `/history`、指南 `/guide`、设置 `/settings`
- 账户切换：后端列出不止一个账户时，顶栏出现日频 / 日内切换，选择记在浏览器 localStorage（键 `ta.account`）；日内账户（ADR 0006）多一个信号页 `/signals`，总览改显示最近信号、不显示评级准确度，历史页没有研判记录
- 设置页（`pages/Settings.tsx`、`llmSettings.ts`）是看板唯一的写入口：切换研判用的深度 / 快速模型和单价（`GET /api/models`、`POST /api/settings/llm`），保存前弹确认，见 ADR 0007
- `src/components/` — Panel、DataTable、RatingChip、EquityChart、Markdown、Debate、Help（`?` 提示）、Welcome 等
