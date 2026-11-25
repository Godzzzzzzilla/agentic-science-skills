# agentic-science-skills

Skills for the Agentic Science product-arena (地质大学分站赛) — scientific reading & writing
tasks on the Playground platform (play.bohrium.com).

Each directory under `skills/` is one self-contained, agent-callable Skill:
`SKILL.md` (valid YAML frontmatter + workflow), deterministic `scripts/` (stdlib-only
engine + one-command audit + selftest), and `references/` (schemas, examples, rationale).

## Skills

| dir | arena | topic |
|---|---|---|
| skills/paper-structured-notes | product-arena-06 | 阅读10｜文献总结与结构化笔记 |
| skills/academic-polish-audit | product-arena-02 | 写作02｜学术语言润色 |
| skills/citation-align-manager | product-arena-03 | 写作04｜参考文献与引用管理 |
| skills/pdf-layout-parse | product-arena-08 | 阅读01｜文献文档解析 |
| skills/translate-with-glossary-lock | product-arena-01 | 阅读03｜文献翻译 |
| skills/claim-grounded-intro | product-arena-04 | 写作08｜引言与相关工作写作 |
| skills/methods-repro-writer | product-arena-05 | 写作09｜方法与实验章节写作 |

Every deliverable is designed around **verifiability**: results carry machine-checkable
anchors (page + char-span + verbatim quote) that a bundled audit script re-verifies
against the source with one command.

## License

MIT.
