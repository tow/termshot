#!/bin/bash
# Smoke tests for the termshot pipeline.
# Run from tool/termshot/: bash tests/run_tests.sh
set -euo pipefail

DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$DIR"
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

echo "=== Test 1: Simple curses TUI (interaction + capture) ==="
python3 interact.py tests/test_simple.yaml -o "$TMPDIR/simple.json"
python3 edit.py "$TMPDIR/simple.json" --print | grep -q "You said: hello from the script"
echo "  ✓ Text interaction captured correctly"

echo ""
echo "=== Test 2: Fancy TUI (box drawing, blocks, truecolor, braille) ==="
python3 interact.py tests/test_fancy.yaml -o "$TMPDIR/fancy.json"

# Verify special characters survived
python3 -c "
import json, sys
d = json.load(open('$TMPDIR/fancy.json'))
text = ''
for row in d['cells']:
    text += ''.join(c['char'] for c in row)

checks = [
    ('Box drawing', '╔' in text and '║' in text and '╗' in text),
    ('Block chars', '▏' in text and '▊' in text and '█' in text),
    ('Braille', '⣀' in text and '⣿' in text),
    ('Check mark', '✓' in text),
    ('Cross mark', '✗' in text),
    ('Loop symbol', '⟳' in text),
    ('Dash line', '───' in text),
]
ok = True
for label, passed in checks:
    print(f'  {\"✓\" if passed else \"✗\"} {label}')
    if not passed:
        ok = False
if not ok:
    sys.exit(1)
"
echo "  ✓ All Unicode characters captured"

# Verify truecolor preserved
python3 -c "
import json, sys
d = json.load(open('$TMPDIR/fancy.json'))
has_truecolor = False
for row in d['cells']:
    for cell in row:
        fg = cell.get('fg', '')
        if len(fg) == 6 and fg != 'default':
            has_truecolor = True
            break
    if has_truecolor:
        break
if not has_truecolor:
    print('  ✗ No truecolor values found')
    sys.exit(1)
print('  ✓ Truecolor values preserved')
"

echo ""
echo "=== Test 3: Render to SVG and HTML ==="
python3 render.py "$TMPDIR/fancy.json" -o "$TMPDIR/fancy.svg" --title "Test Dashboard"
python3 render.py "$TMPDIR/fancy.json" -o "$TMPDIR/fancy.html" --title "Test Dashboard"

# Verify SVG contains key elements
python3 -c "
import sys
svg = open('$TMPDIR/fancy.svg').read()
checks = [
    ('SVG has box drawing', '╔' in svg),
    ('SVG has block chars', '▏' in svg),
    ('SVG has braille', '⣿' in svg),
    ('SVG has truecolor', '#64b4ff' in svg),
    ('SVG has bg gradient', 'fill=\"#' in svg),
]
ok = True
for label, passed in checks:
    print(f'  {\"✓\" if passed else \"✗\"} {label}')
    if not passed:
        ok = False
if not ok:
    sys.exit(1)
"
echo "  ✓ SVG and HTML rendered correctly"

echo ""
echo "=== Test 4: Edit pipeline ==="
python3 edit.py "$TMPDIR/fancy.json" --replace-all "72%" "99%" -o "$TMPDIR/edited.json"
python3 edit.py "$TMPDIR/edited.json" --print | grep -q "99%"
echo "  ✓ Text replacement works"

python3 render.py "$TMPDIR/edited.json" -o "$TMPDIR/edited.svg" --title "Edited"
echo "  ✓ Edited version renders"

echo ""
echo "All tests passed."
