#!/bin/bash
echo "=== assets ==="
ls -la /var/www/main-site/assets/
echo "=== wrap rule in built css ==="
sudo grep -o "\.vapp-fullscreen-background[^{]*v-application__wrap[^{]*{[^}]*}" /var/www/main-site/assets/*.css | head -5
echo "=== any wrap rules mentioning data-v ==="
sudo grep -c "v-application__wrap\[data-v" /var/www/main-site/assets/*.css
