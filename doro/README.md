# doro 表情包工作目录

原图 ＋ 一张总表 `manifest.txt` ＋ 两个脚本。加图、改图注、改映射都在本地做完，不用重启网关。

| 文件 | 作用 |
| --- | --- |
| `doro/doro_N.gif` | 表情包原图（都在 `doro/doro/` 子目录），编号就是映射和工具枚举里用的 id |
| `manifest.txt` | **总表**：`id \| 画面 \| 适用场景 \| 已映射`，唯一需要手改的文件 |
| `sync-stickers.py` | 推到线上：图片 → `manifest.json` → emoji 映射 |
| `rename-stickers.py` | 按顺序重命名成 `doro_1..doro_N`，顺带改总表里的引用 |

挑 emoji 看 `documents/EMOJI_LIST.md`。

## 填表规矩

- `画面` 必填、`适用场景` 可空；两列合成 `画面：适用场景` 给模型看，别在这两列写 emoji 或竖线。
- `已映射` 写 emoji，多个空格隔开；`--` 表示还没映射。必须是完整 emoji：别连写 `🤗😄`
  （会被当成一个键，永远匹配不到），别写 `❤`／肤色修饰符／组合 emoji 的片段，脚本会拦。
- **行序＝优先级**：一条回复里同时出现多个已映射 emoji 时只补最靠前那张，其余从正文摘掉但不补图。
  id 列不要求升序，想调优先级就调行号。
- 没列进表的图不会上传；单张图 ≤ 2 MiB。

## 常用命令

```
python doro\sync-stickers.py                          # 预览，什么都不写
python doro\sync-stickers.py --apply                  # 图 + manifest + 映射一次推完
python doro\sync-stickers.py --apply --only mapping   # 只改映射（最常用）
python doro\sync-stickers.py --apply --only images    # 只处理图与 manifest
python doro\sync-stickers.py --apply --prune          # 顺带删线上本地已不收录的图
python doro\sync-stickers.py --list                   # 只读：谁还没映射
python doro\rename-stickers.py [apply]                # 重命名预览／执行
```

加新图：图丢进 `doro/doro/` → `rename-stickers.py apply` → 表里补一行 → `sync-stickers.py --apply`。
顺序不能反：写映射会拿 id 核 `manifest.json`，图没上线会被拦下。

## 出问题怎么读

| 输出 | 意思 |
| --- | --- |
| `线上与本地完全一致` | 没事可做 |
| `这是预览` | 默认不写，确认后加 `--apply` |
| `有 N 个问题，未做任何改动` | 缺图／id 重复／超 2 MiB／第四列写法不对，逐条看 |
| `这些 id 线上 manifest 里没有` | 先 `--apply --only images`，再写映射 |
| `自检失败，已恢复备份` | 配置已回滚，把输出发我 |

写前自动备份、写后逐条自检、失败自动回滚；配置热加载，下一轮聊天生效。素材库变了而老会话
还看不到新 id 时发 `/new`。emoji→表情包只对 QQ／微信私聊的短回复（≤3 行、≤200 字、
无代码块）生效，一回合最多一张，冷却 300 秒，与 `send_sticker` 共用同一计时器。
