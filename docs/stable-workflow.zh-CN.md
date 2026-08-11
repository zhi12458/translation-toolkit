# 稳定翻译工作流：安装、操作与发布门槛

本工具包由 Agent 技能、SQLite 术语库、Djot 转换脚本和机械门禁组成。
它不会自动判断佛法义理是否正确；公开发布仍需要独立审校和具名人工批准。

## 1. 安装

### 最小安装（已有 `source.dj` 和 `target.dj`）

只运行术语搜索、双语生成和 Python 门禁时，需要 Python 3.11 或更高版本、Git 和
SQLite。Python 3.11–3.14 已在本地或 CI 覆盖：

```sh
python3 --version
git --version
sqlite3 --version
python3 scripts/doctor.py --minimal
```

### macOS Apple Silicon 完整安装

```sh
brew install uv fish jq pandoc typst poppler herdr
brew install can1357/tap/omp

python3 scripts/doctor.py --strict
```

完整模式包括：DOCX ↔ Djot、Typst PDF、PDF 文本抽取、OMP 和 Herdr。
工具包命令不会自动安装这些系统程序。可选的 Flask 术语库 UI 使用 `uv run`；第一次
启动可能联网解析并缓存 Flask，离线使用前需先准备好缓存。

### Linux 补充（Debian/Ubuntu）

首期以 macOS Apple Silicon 为主；Linux 可先安装发行版提供的基础工具：

```sh
sudo apt update
sudo apt install python3 git sqlite3 fish jq pandoc poppler-utils
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Typst、OMP 与 Herdr 请按各自官方发布页安装，并在最后运行
`python3 scripts/doctor.py --strict`。不同发行版的软件版本可能较旧；若转换或
排版测试失败，先比对官方当前版本。Windows 暂不作为首期支持目标。

### Codex 加载技能

Codex 当前使用仓库级 `.agents/skills` 或用户级 `~/.agents/skills`。选择以下其中一个
`skill_root`；项目级路径会把私人项目政策限制在该项目内。命令不会覆盖已有技能：

```sh
toolkit=/Users/jingzhi/puti/translation-toolkit
skill_root="$HOME/.agents/skills"
# 或仅供一个私人项目使用：
# skill_root=/absolute/path/to/private-project/.agents/skills
mkdir -p "$skill_root"

for skill_dir in "$toolkit"/skills/*; do
  test -f "$skill_dir/SKILL.md" || continue
  target="$skill_root/$(basename "$skill_dir")"
  if test -e "$target" || test -L "$target"; then
    echo "保留已有路径：$target"
  else
    ln -s "$skill_dir" "$target"
  fi
done
```

换机器时必须把 `/Users/jingzhi/puti/translation-toolkit` 换成实际绝对路径。
官方说明：[Codex Build skills](https://learn.chatgpt.com/docs/build-skills)。

### OMP + Herdr

```sh
omp config set skills.customDirectories \
  '["/Users/jingzhi/puti/translation-toolkit/skills"]'
omp config get skills.customDirectories --json

herdr integration install omp
herdr integration status
```

一个文章目录对应一个 pane。独立审校使用另一会话，不复用首译上下文：

```sh
herdr agent start review-book --kind omp --pane "$PANE_ID" -- \
  --cwd /absolute/path/to/article
herdr agent wait review-book --timeout 3600000
```

上述命令使用 OMP 已配置的默认模型。若需要专用审校模型，先在 OMP 中确认该模型或
role 已配置，再向 `herdr agent start` 的 `--` 后增加 `--model '<已配置名称>'`；不要照抄
只存在于其他机器的私有别名。

参考：[OMP](https://github.com/can1357/oh-my-pi)、
[Herdr](https://github.com/herdrdev/herdr)、
[uv 安装](https://docs.astral.sh/uv/getting-started/installation/)。

## 2. 创建并翻译一篇文章

```sh
mkdir -p ../translate-files/my-article
cd ../translate-files/my-article
```

将 Word 原稿转换为 Djot：

```sh
/Users/jingzhi/puti/translation-toolkit/scripts/docx2dj.fish \
  original.docx source.dj
```

先填写四类项目记录：

1. `translation-project.yaml`：作者/译者、体裁、受众、语域、文化桥接政策、经文版本、工具版本和发布批准。
2. `term-map.yaml`：每个中文词冻结一个本项目义项，并记录正式/允许/禁用译法、来源和人工确认状态。
3. `review-findings.jsonl`：独立审校问题、严重度和处理状态。
4. `qa-report.json`：机械门禁的 PASS/WARN/SKIP/FAIL 结果。

字段定义见 `schemas/`，可复制 `examples/minimal-article/` 开始。为避免新增 YAML
依赖，门禁读取的 YAML 文件采用 JSON 语法书写的 YAML 1.2 子集；示例可直接复制。历史
`term-map.md` 仍向后兼容，但新项目只维护 `term-map.yaml`。

搜索并冻结高风险术语：

```sh
/Users/jingzhi/puti/translation-toolkit/terms-database/search.py '空性'
/Users/jingzhi/puti/translation-toolkit/terms-database/search.py \
  '空性 src:DoT定稿' 10
```

首译前把 `translation-project.yaml`、`source.dj` 和冻结术语提供给 Agent。译文必须写到
`target.dj`，并保持每行空白位置与 `source.dj` 对齐。

生成双语稿：

```sh
/Users/jingzhi/puti/translation-toolkit/scripts/gen-bilingual.py \
  source.dj target.dj --output bilingual.dj
```

若行数或空行位置错位，生成器会在写出正文前失败。

## 3. 审校与发布

先自审，再由独立会话审校。公开发布、经文引用密集或义理敏感内容必须满足：

- `term-map` 已冻结且没有 `needs_human` 项；
- 冻结术语覆盖率不低于 99%；
- `review-findings.jsonl` 没有未解决的 `critical` 或 `major`；
- 严格机械门禁零 FAIL、零 SKIP；
- 具名人工批准者明确批准。

运行 strict 前，把 `release.level` 设为 `public` 或 `sensitive`，并如实填写独立
审校者和批准者。不得为了让门禁通过而虚构签名。

严格门禁：

```sh
/Users/jingzhi/puti/translation-toolkit/scripts/check-translation.py \
  . --strict --json --output qa-report.json
```

草稿模式允许明确显示 WARN/SKIP：

```sh
/Users/jingzhi/puti/translation-toolkit/scripts/check-translation.py . --json
```

机械门禁只证明结构、格式、数字、术语映射和派生文件一致；它不证明译文的义理、语气、
流畅度或经文版本选择正确。

批准后导出：

```sh
/Users/jingzhi/puti/translation-toolkit/scripts/dj2docx.fish \
  target.dj /tmp/my-article-en.docx
```

若文章目录已经准备好可编译的 Typst 入口文件（模板、字体和图片路径均可用），再导出
PDF：

```sh
/Users/jingzhi/puti/translation-toolkit/scripts/compile-typst.fish \
  my-article.typ /tmp/my-article-en.pdf
```

## 4. 公开微型验收

仓库自带不含私人译稿的最小样例：

```sh
cd /Users/jingzhi/puti/translation-toolkit
python3 scripts/doctor.py --minimal

./scripts/gen-bilingual.py \
  examples/minimal-article/source.dj \
  examples/minimal-article/target.dj \
  --output examples/minimal-article/bilingual.dj

./scripts/check-translation.py examples/minimal-article --strict --json \
  --output examples/minimal-article/qa-report.json
```

成功后删除两个生成文件即可；它们已由 `.gitignore` 排除。

## 5. Codeberg CI

`.woodpecker.yml` 会在 Python 3.11–3.13 运行编译、测试和 Fish 语法检查。Codeberg 的托管
Woodpecker 需要维护者在 `ci.codeberg.org` 申请并启用仓库；仅提交配置文件不会自动开通服务。
参见 [Codeberg CI 官方说明](https://docs.codeberg.org/ci/)。

## 6. 旧子模块

相邻 `mpi-translations` 仓库的 `.gitmodules` 仍指向旧 SourceHut 地址。短期继续使用本目录的
独立 Codeberg 克隆。正式迁移时，应在私有仓库中把子模块 URL 改为：

```sh
git config -f .gitmodules submodule.toolkit.url \
  https://codeberg.org/eastwind/translation-toolkit.git
git submodule sync -- toolkit
git submodule update --init toolkit
TOOLKIT_COMMIT='paste-reviewed-full-sha-here'
git -C toolkit fetch origin
git -C toolkit checkout "$TOOLKIT_COMMIT"
test "$(git -C toolkit rev-parse HEAD)" = "$TOOLKIT_COMMIT"
git submodule status
git add .gitmodules toolkit
```

把 `TOOLKIT_COMMIT` 换成维护者已审计并发布的完整提交 SHA，再把 `.gitmodules` 与新的
submodule gitlink 一起提交，才能真正固定版本。此操作会修改私有仓库；本次工具包优化
不会替用户执行。
