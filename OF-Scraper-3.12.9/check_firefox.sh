#!/bin/bash
echo "=== Firefox cookie files ==="
find ~/ -name 'cookies.sqlite' -path '*firefox*' 2>/dev/null

echo ""
echo "=== Firefox executable ==="
which firefox 2>/dev/null || echo "Not in PATH"
readlink -f "$(which firefox 2>/dev/null)" 2>/dev/null

echo ""
echo "=== Standard profile dir ==="
ls -la ~/.mozilla/firefox/ 2>/dev/null || echo "Not found"

echo ""
echo "=== Snap profile dir ==="
ls -la ~/snap/firefox/common/.mozilla/firefox/ 2>/dev/null || echo "Not found"
ls -la ~/snap/firefox/ 2>/dev/null || echo "Not found"

echo ""
echo "=== Flatpak profile dir ==="
ls -la ~/.var/app/org.mozilla.firefox/.mozilla/firefox/ 2>/dev/null || echo "Not found"

echo ""
echo "=== Firefox install type ==="
dpkg -l firefox 2>/dev/null | tail -1
snap list firefox 2>/dev/null
flatpak list 2>/dev/null | grep -i firefox

echo ""
echo "=== All firefox-related profile dirs ==="
find ~/ -name 'profiles.ini' -path '*firefox*' 2>/dev/null