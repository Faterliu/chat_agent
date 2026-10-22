# -*- coding: utf-8 -*-
"""修正 app.less 的高度链规则：后代选择器必须用 :deep()。
本文件构建时会被内联进 App.vue 的 scoped 样式，选择器会带上 [data-v-xxx]；
.v-application__wrap 由 Vuetify 内部渲染、不带该属性，直接写后代选择器永不匹配。
"""
import io
import sys

P = '/opt/leleo-home-page/public/css/app.less'

with io.open(P, encoding='utf-8') as f:
    src = f.read()

pairs = [
    (
        '.vapp-fullscreen-background > .v-application__wrap {',
        '.vapp-fullscreen-background > :deep(.v-application__wrap) {',
    ),
    (
        '   这里把 wrap 拉回「跟 v-app 一样高」，让 .home-scroll 的 height:100% 真正等于窗口高。 */',
        '   这里把 wrap 拉回「跟 v-app 一样高」，让 .home-scroll 的 height:100% 真正等于窗口高。\n'
        '   ⚠️ 必须写成 :deep()：本文件在构建时被内联进 App.vue 的 <style scoped>，\n'
        '   选择器会被加上 [data-v-xxx]；而 .v-application__wrap 是 Vuetify 内部渲染的节点，\n'
        '   身上没有该属性 —— 直接写后代选择器会永远不匹配（2026-09-22 修正）。 */',
    ),
]

for old, new in pairs:
    n = src.count(old)
    print('match=%d for: %s' % (n, old[:48]))
    if n != 1:
        print('ABORT: expected exactly 1 occurrence')
        sys.exit(1)
    src = src.replace(old, new)

with io.open(P, 'w', encoding='utf-8', newline='') as f:
    f.write(src)

print('written, bytes=%d' % len(src.encode('utf-8')))
