# doro 表情包工作目录

这里放表情包原图、两份可编辑的 txt 和三个脚本。加图、改图注、改映射都能自己做完，
不用重启网关，也不用找人。

| 文件 | 作用 |
| --- | --- |
| `doro_1.gif` … `doro_N.gif` | 表情包原图，编号就是映射和工具枚举里用的 id |
| `manifest.txt` | **表情包索引**：`id \| 文件名 \| 场景说明`，决定哪些图上线、模型看到的说明 |
| `mapping.txt` | **emoji 映射**：`emoji -> doro_N`，决定哪些 emoji 会被换成图 |
| `sync-stickers.py` | 按 `manifest.txt` 上传图片并重建服务器上的 `manifest.json` |
| `apply-mapping.py` | 按 `mapping.txt` 写入网关的表情包映射配置 |
| `rename-stickers.py` | 把目录里的图按顺序重命名成 `doro_1..doro_N`，并同步改两份 txt |

挑 emoji 看项目根目录的 `documents/EMOJI_LIST.md`（按情绪分组、带码点、含每张图的现状）。

## 一、加一张新图（四步）

```
1. 把图丢进本目录（文件名随便）
2. python doro\rename-stickers.py --apply    # 重命名成 doro_N，并改好两份 txt
3. 在 manifest.txt 里补一行：doro_N | doro_N.gif | 这张图的场景说明
4. python doro\sync-stickers.py --apply      # 上传 + 重建 manifest
```

第 3 步的「场景说明」是给模型挑图看的，写得越具体它选得越准，比如
`趴着 >_< 不想动：摆烂、逃避、累到不想说话`。不写就不会上传（脚本会提醒）。

## 二、改 emoji 映射（最常用）

1. 编辑 `mapping.txt`：`emoji -> 表情包id    # 说明`
2. `python doro\apply-mapping.py`（加 `--dry-run` 只看差异，`--list` 看线上有哪些 id）

生效时机：**下一轮聊天**，不用重启。写前自动备份，写后逐条自检，失败自动回滚。

### mapping.txt 的规矩

- 连字符写 `->` 或 `→` 都行；`#` 后面是注释。
- 一行可以写多个 emoji（空格／逗号／顿号分隔），它们给同一张图。
- 同一个 id 可以出现在多行（多对一，比如 `🤗` 和 `😄` 都给 `doro_12`）。
- **行顺序就是优先级**：一条回复里同时出现多个已映射 emoji 时，只补最靠前那张。
- 左边必须是完整的一个 emoji。别写 `❤`（客户端会补成 `❤️`，只写半个会把后面拆坏），
  别写肤色修饰符，也别写组合 emoji 的其中一段——脚本会直接拦下来。

## 三、重命名

```
python doro\rename-stickers.py           # 预览旧名 → 新名
python doro\rename-stickers.py apply     # 真正改名（--apply、-a 等价）
```

默认按已有的 `doro_N` 排序，没有编号的接在后面（`--order name|mtime` 可换规则）。
两阶段改名不会撞名，写 `rename-log-<时间>.txt` 记录怎么还原；编号变了会同步改
`mapping.txt` 和 `manifest.txt` 里的引用（留 `.bak-<时间>` 备份），
按 token 精确匹配，`doro_1` 不会误伤 `doro_14`。

## 四、sync-stickers.py 会做什么

- 比对本地与服务器的 sha256，只传新增／改过的图；
- 校验单文件 1 B–2 MiB（工具层硬限制）、扩展名、`manifest.txt` 里的 id 与文件名；
- manifest.txt 没收录的图不会上传，服务器上多出来的文件默认不删（`--prune` 才删）；
- 上传后核对大小与 sha256、把文件权限设成 0600，再整份重建 `manifest.json`（0600）；
- 用线上 `tools.sticker_tool.load_manifest()` 复核每条都能读，并打印工具说明长度
  （这段每轮都随 schema 发给模型，条目越多越贵）。

## 五、常见提示怎么读

| 输出 | 意思 |
| --- | --- |
| `与线上完全一致，不用改` | 已经生效，什么都不用做 |
| `目录里没收录（不会上传）` | 图没写进 `manifest.txt` |
| `manifest.txt 收录 N 张` | 这次会同步 N 条 |
| `有 N 个问题，未做任何改动` | 缺图、id 重复、超 2 MiB 等，逐条列出来了 |
| `X 是 Y 的一部分` | 两个 emoji 有包含关系，只保留完整的那个 |
| `自检失败，已恢复备份` | 写入后线上模块没按预期摘 emoji，配置已回滚，把输出发我 |
| `如果模型还没看到新 id，发 /new` | 工具枚举已更新，但老会话的 schema 是旧的 |

## 六、生效范围（改之前先知道）

emoji→表情包只对 **QQ 私聊的短回复**（≤3 行、≤200 字、不含代码块）生效；
微信、长回复、代码块一律原样不动。一回合最多补一张，冷却 300 秒，
与模型主动调 `send_sticker` 共用同一个冷却计时器（工具优先）。
