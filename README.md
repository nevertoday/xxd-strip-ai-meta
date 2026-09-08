# xxd-strip-ai-meta

批量清除图片中的 AI 来源标记和元数据，可作为独立命令行工具或 AI Agent Skill 使用。

通过 ExifTool 清理受支持的 C2PA / Content Credentials、OpenAI / gpt-image 来源信息，以及 EXIF、XMP、IPTC、注释等元数据。默认保留 ICC 色彩配置和文件修改时间，不解码、重编码图片像素。

这是元数据清理工具：不能去除画面中可见的水印，也不能保证清除像素级隐形水印、平台指纹或服务器端标记。适用于隐私保护、内部处理与元数据整理，请勿用于误导他人对图片来源的判断。

## 安装

需要 Python 3.10+ 和 PATH 中可用的 ExifTool，无第三方 Python 依赖。

```bash
git clone https://github.com/nevertoday/xxd-strip-ai-meta.git
cd xxd-strip-ai-meta
```

macOS 使用 `brew install exiftool`；Debian / Ubuntu 使用 `sudo apt install libimage-exiftool-perl`。Windows 可从 [ExifTool 官网](https://exiftool.org/) 安装并配置 PATH。使用 `python3 --version` 和 `exiftool -ver` 检查环境；Windows 的 Python 命令可能是 `python`。

## 使用

以下命令从仓库根目录运行。默认会直接修改原文件，首次使用建议先预览，再保留备份执行：

```bash
# 只列出文件
python3 scripts/clean_image_provenance.py /path/to/images --dry-run

# 清理并保留 ExifTool 的 *_original 备份
python3 scripts/clean_image_provenance.py /path/to/images --backup

# 多文件、多目录可以混合传入
python3 scripts/clean_image_provenance.py /path/to/a.png /path/to/folder-a /path/to/folder-b

# 大批量任务：后台运行并输出日志及监控命令（适用于 POSIX shell）
python3 scripts/clean_image_provenance.py /path/to/images --background
```

| 参数 | 说明 |
| --- | --- |
| `--dry-run` | 预览，不修改文件 |
| `--backup` | 保留原文件备份 |
| `--jobs 5` | 默认 5 个并发批次；设为 1 降低负载 |
| `--chunk-size 100` | 每批文件数，默认 100 |
| `--log-file PATH` | 指定日志文件 |
| `--background` | 启动后台任务，输出停止及日志查看命令 |
| `--drop-color-profile` | 同时删除 ICC 配置，可能影响色彩显示 |
| `--no-verify` | 跳过清理后的元数据标记检查 |

递归查找 PNG、JPEG、WebP、TIFF、HEIC、HEIF 和 AVIF；具体写入能力取决于 ExifTool 和文件格式。自动去重重叠输入，跳过隐藏子目录及常见缓存目录，默认跳过已识别的扩展名与文件头不匹配的文件。仅接受本地文件或目录，不直接接受远程链接或压缩包。

验证是对 ExifTool 输出中的来源关键字进行检查，不是通用水印检测。退出码：`0` 表示没有报告清理失败或残留（也可能没有找到文件），`1` 表示清理失败，`2` 表示发现残留标记。请同时查看日志中的跳过和缺失文件提示。

## 作为 Skill 安装

将此仓库克隆到所用 Agent 的技能目录，例如 Claude Code：

```bash
git clone https://github.com/nevertoday/xxd-strip-ai-meta.git ~/.claude/skills/xxd-strip-ai-meta
```

已有同名目录时请先备份或使用其他位置。技能入口为 `SKILL.md`；Agent 应从安装目录运行脚本，或解析脚本的绝对路径。

## 许可证

MIT，详见 [LICENSE](LICENSE)。ExifTool 为单独安装的依赖，遵循其自身许可证。
