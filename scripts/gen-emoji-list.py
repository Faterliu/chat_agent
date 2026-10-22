# -*- coding: utf-8 -*-
"""生成 documents/EMOJI_LIST.md：按情绪分组的 emoji 清单（码点由脚本计算，避免手写错）。

用途：用户挑选要映射成 doro 表情包的 emoji。只读生成本地文档，不接触服务器。
运行：python scripts/gen-emoji-list.py
"""
from pathlib import Path

GROUPS: list[tuple[str, str, list[str]]] = [
    (
        "开心 / 笑",
        "笑、高兴、被逗乐；适合 doro_5（弹吉他）、doro_12（转圈）",
        "😀 😃 😄 😁 😆 😅 😂 🤣 🙂 😊 😇 😉 😌 😋 😛 😜 🤪 😝 🤗 🤭 😍 🤩 🥳".split(),
    ),
    (
        "得意 / 炫耀",
        "被夸、占上风、小得瑟；适合 doro_2（扭腰得瑟）",
        "😎 😏 🤩 😜 😝 🥳 😼 🤙".split(),
    ),
    (
        "哭 / 难过 / 委屈",
        "难受、累垮、被打击；适合 doro_3（跪地去世）、doro_13（提橘子重逢）",
        "😢 😭 🥲 😞 😔 😟 😕 😩 😫 😣 😖 🥹 😿 💔 🥀".split(),
    ),
    (
        "生气 / 不满",
        "气鼓鼓但多半是玩笑；适合 doro_4（轻锤一下）、doro_8（举手要打）",
        "😠 😡 🤬 😤 💢 😾 👊 😒".split(),
    ),
    (
        "无语 / 摇头 / 疑惑",
        "反驳、看不过去、想不通；适合 doro_6（摇头 no no）、doro_10（托腮苦想）",
        "🙄 😒 😑 😐 😶 🤔 🤨 🧐 😵‍💫 🤷 🤦 🫤".split(),
    ),
    (
        "看戏 / 围观",
        "吃瓜、等下文、纯围观；适合 doro_9（抱爆米花）",
        "👀 🍿 🎬 📺 🫣 🍉".split(),
    ),
    (
        "惊讶 / 震惊",
        "意外、被惊到；库里没有强对应，可选 doro_10",
        "😮 😲 😱 😯 😦 😧 🤯 😳 🙀".split(),
    ),
    (
        "害怕 / 紧张",
        "不安、发怵；库里没有强对应，多与 doro_10 或纯文字搭配",
        "😨 😰 🫣 😬 🥶 😖 😣".split(),
    ),
    (
        "害羞 / 撒娇 / 可爱",
        "被夸得不好意思、撒娇、装乖；适合 doro_14（骑弹簧木马）、doro_12（转圈）",
        "🥺 😳 😊 😚 🤭 🫶 🥹 🐣 💕 ✨ 🌸".split(),
    ),
    (
        "爱 / 感谢 / 亲昵",
        "喜欢、感谢、亲昵；库里无对应，一般保留原 emoji 更好",
        "❤️ 🧡 💛 💚 💙 💜 🤍 🖤 💕 💞 💓 💗 💘 💝 💟 ❤️‍🔥 💋 😘 🙏 🤝 🫂".split(),
    ),
    (
        "赞同 / 确认 / 鼓励",
        "同意、收到、打气；库里无对应，建议保留",
        "👍 👎 👌 ✌️ 🤞 🤟 🤘 🙆 🙅 🙋 🫡 👏 🙌 💯 ✅ ☑️ ✔️ ✊ 💪".split(),
    ),
    (
        "累 / 困 / 上班",
        "加班、撑不住、想躺；适合 doro_7（趴桌敲键盘）、doro_3（跪地）",
        "😪 😴 🥱 💤 🫠 😮‍💨 😵 😵‍💫 🥲 💻 ⌨️ 🛋️ 📝".split(),
    ),
    (
        "吃 / 喝 / 休闲",
        "吃喝、放松、晃悠；适合 doro_5（弹吉他）、doro_11（骑小黄鸭）",
        "🍚 🍜 🍲 🍡 🍰 🍪 🍿 ☕ 🍺 🥤 🍊 🎮 🎵 🎶 🎧 🎸 🛌".split(),
    ),
    (
        "庆祝 / 打气",
        "赢了、搞定了；库里无强对应",
        "🎉 🎊 🏆 🚀 🌟 ⭐️ 🔥 🌈 🍀".split(),
    ),
    (
        "收尾 / 敷衍 / 再见",
        "没话说、要走了；库里无强对应，慎映射（易显得冷淡）",
        "🙂 😐 👋 🤐 🫡 💤".split(),
    ),
    (
        "物件 / 动物（可拟人）",
        "想表达具体场景时用；可对应 doro_13（🍊）、doro_5（🎸）、doro_7（💻）",
        "🐶 🐱 🐷 🐟 🦆 🐥 🧸 🎠 🖥️ 🍊 🎸 🎀 🕯️".split(),
    ),
]

STICKERS: list[tuple[str, str, str, str, str]] = [
    ("doro_1", "黄色小动物睡衣歪头卖萌", "撒娇、求关注、被夸得不好意思", "", "🥰 ✨ 🌸 🐣 😊"),
    ("doro_2", "得瑟、扭腰炫耀", "被夸、占了上风、小得意", "😎", "😏 😜 🤩 🥳 😼"),
    ("doro_3", "跪地去世", "我很难受、累死了、被打击到", "😭", "😩 😫 🥲 😣 😞 💔"),
    ("doro_4", "轻轻锤你一下", "玩笑式生气、气鼓鼓但没真生气", "😤", "😠 💢 😒 👊"),
    ("doro_5", "悠闲弹吉他", "心情好、放松、哄人开心", "😊", "😌 🎵 🎶 🎸"),
    ("doro_6", "摇头 no no", "不是这样、你说错了，温和反驳", "🙄", "😕 🤨 😒 😑 🤷"),
    ("doro_7", "趴桌敲键盘", "辛苦工作中、加班赶活", "😪", "😩 💻 😮‍💨 🥱"),
    ("doro_8", "举手要打你", "玩笑生气、追着打", "😡 😠", "🔨 💢 😾"),
    ("doro_9", "抱着爆米花吃", "悠闲看戏、吃瓜、等下文", "👀", "🍿 🍉 🫣 🎬"),
    ("doro_10", "托腮苦想", "想不明白、有点不正经的思考", "🤔 🤨", "🧐 😵‍💫 🫤"),
    ("doro_11", "骑小黄鸭木马", "悠闲晃悠、没事干", "😌", "🛋️ 😴 🫠 🎠 🍡"),
    ("doro_12", "双手放胸前转圈", "没意义但可爱、撒娇、开心", "🤗 😄", "✨ 🥰 😚 🫶"),
    ("doro_13", "车站重逢、提着橘子", "久别再见、略微伤感", "🥹", "🥲 🫂 🍊 😿"),
    ("doro_14", "骑弹簧小木马", "没意义但可爱、单纯开心", "🥺", "🥰 🤗 😊 🐣 ✨"),
    ("doro_15", "张大嘴嚎啕大哭", "委屈崩了、太难了、好想哭", "", "😢 😫 😖 😭 🥲"),
    ("doro_16", "趴着 >_< 不想动", "摆烂、逃避、累到不想说话", "", "🫠 😩 😮‍💨 💤"),
    ("doro_17", "鼓脸冒火「生气气」", "假生气、闹小脾气、气鼓鼓", "", "💢 😾 😠 😤"),
    ("doro_18", "躲灯旁探头偷看", "暗中观察、默默等你、静静待着", "", "🫣 👀 🍉"),
]

# 线上映射表顺序（＝一回合出现多个已映射 emoji 时的优先级）
CURRENT_ORDER: list[tuple[str, str, str]] = [
    ("\U0001F62D", "doro_3", "很难受"),
    ("\U0001F60E", "doro_2", "得瑟"),
    ("\U0001F644", "doro_6", "无语"),
    ("\U0001F440", "doro_9", "看戏"),
    ("\U0001F97A", "doro_14", "撒娇"),
    ("\U0001F624", "doro_4", "气鼓鼓"),
    ("\U0001F60A", "doro_5", "满足"),
    ("\U0001F62A", "doro_7", "困乏"),
    ("\U0001F621", "doro_8", "愤怒"),
    ("\U0001F620", "doro_8", "生气"),
    ("\U0001F914", "doro_10", "思考"),
    ("\U0001F928", "doro_10", "怀疑"),
    ("\U0001F917", "doro_12", "抱抱"),
    ("\U0001F60C", "doro_11", "放松"),
    ("\U0001F979", "doro_13", "忍住眼泪"),
    ("\U0001F604", "doro_12", "笑"),
]


def cps(emoji: str) -> str:
    return " ".join("U+%04X" % ord(ch) for ch in emoji)


def main() -> None:
    lines: list[str] = []
    add = lines.append

    add("# emoji → doro 表情包 映射清单（2026-10-22）")
    add("")
    add("用来挑映射：左边是你想摘掉的 emoji，右边是要补发的表情包。本文件只是清单，")
    add("实际生效的是 `HERMES_HOME/config.yaml` 里的 `display.emoji_stickers.mapping`。")
    add("")
    add("## 一、18 张图的映射现状（2026-10-22；doro_1、15-18 已上线待映射）")
    add("")
    add("「已映射」是线上生效的 emoji；「—」表示这张图还没有 emoji 指向它；右列「备选」供参考。")
    add("")
    add("| id | 画面 | 适用场景 | 已映射 | 备选 |")
    add("| --- | --- | --- | --- | --- |")
    for sid, look, scene, cur, cand in STICKERS:
        add(f"| `{sid}` | {look} | {scene} | {cur or '—'} | {cand} |")
    add("")
    add("一张图可以对应多个 emoji（多对一没问题，比如 `😡` 和 `😠` 都给 `doro_8`）。")
    add("")
    add("## 二、按情绪分组的 emoji 全集")
    add("")
    add("标「组合」的是多码点 emoji（带变体选择符、ZWJ 或肤色修饰），**必须整段复制**，")
    add("少一个码点就匹配不上。")
    add("")
    add("| emoji | 码点 | | emoji | 码点 |")
    add("| --- | --- | --- | --- | --- |")
    for title, note, items in GROUPS:
        add(f"| **{title}** | {note} | | | |")
        half = (len(items) + 1) // 2
        left, right = items[:half], items[half:]
        for i in range(half):
            l = left[i]
            lc = cps(l) + (" （组合）" if len(l) > 1 else "")
            if i < len(right):
                r = right[i]
                rc = cps(r) + (" （组合）" if len(r) > 1 else "")
                add(f"| {l} | {lc} | | {r} | {rc} |")
            else:
                add(f"| {l} | {lc} | | | |")
        add("|  |  | |  |  |")

    add("")
    add("## 三、匹配规则的三个坑（重要）")
    add("")
    add("1. **按子串匹配**：逻辑是 `if emoji in line` 再 `line.replace(emoji, \"\")`。")
    add("   所以映射的必须是完整的那个字符：别写 `❤`（会把 `❤️` 拆坏只剩变体符）、")
    add("   别写单个肤色修饰符 `🏻`，也别写多码点组合的其中一段。")
    add("2. **一回合只补一张**：同一条回复里出现多个已映射 emoji 时，按**映射表的书写顺序**")
    add("   取第一个命中的（不是按句子里的先后），其余 emoji 也会被摘掉但不再补图。")
    add("   所以多个 emoji 映射到不同图时，把最想出现的那条写在前面。")
    add("   当前 15 条的先后顺序见第四节的配置片段，越靠前优先级越高。")
    add("3. **只管短回复**：整条超过 3 行、超过 200 字、或含代码块，一律原样不动。")
    add("")
    add("## 四、线上配置（也就是优先级顺序）")
    add("")
    add("当前 15 条，顺序即优先级。想加想换照这个格式发我（改完不用重启）：")
    add("")
    add("```yaml")
    add("display:")
    add("  emoji_stickers:")
    add("    enabled: true")
    add("    platforms: [qqbot]")
    add("    mapping:")
    for emoji, sid, label in CURRENT_ORDER:
        add(f'      "{emoji}": {sid.ljust(7)} # {label}')
    add("    max_per_turn: 1")
    add("    cooldown_seconds: 300")
    add("    max_lines: 3")
    add("    max_chars: 200")
    add("```")
    add("")
    add("冷却 300 秒是全进程共享的，`send_sticker` 工具发过图也会占用这个冷却。")
    add("")

    out = Path(__file__).resolve().parent.parent / "documents" / "EMOJI_LIST.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    total = sum(len(items) for _, _, items in GROUPS)
    print("written:", out)
    print("groups:", len(GROUPS), "emoji cells:", total, "lines:", len(lines))


if __name__ == "__main__":
    main()
