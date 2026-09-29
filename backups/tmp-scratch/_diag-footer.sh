#!/bin/bash
# 诊断：线上产物是否包含备案号渲染逻辑
D=/var/www/main-site
echo "=== index.html mtime ==="
stat -c '%y' $D/index.html
echo "=== assets ==="
ls -la $D/assets/
echo "=== grep filing-record in css ==="
grep -l "filing-record" $D/assets/*.css 2>/dev/null || echo "NOT FOUND in css"
echo "=== grep filing-record in js ==="
grep -l "filing-record" $D/assets/*.js 2>/dev/null || echo "NOT FOUND in js"
echo "=== grep icpStatements in js ==="
grep -o "icpStatements" $D/assets/*.js 2>/dev/null | sort -u || echo "NOT FOUND icpStatements"
echo "=== grep beian link in js ==="
grep -o "beian.miit.gov.cn" $D/assets/*.js 2>/dev/null | sort -u || echo "NOT FOUND beian link"
echo "=== src mtime ==="
stat -c '%y %n' /opt/leleo-home-page/src/components/sections/ProjectsSection.vue
echo "=== dist mtime in src tree ==="
stat -c '%y %n' /opt/leleo-home-page/dist/assets/ 2>/dev/null || echo "no dist assets"
ls -la /opt/leleo-home-page/dist/assets/ 2>/dev/null | head -20
