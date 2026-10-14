#!/usr/bin/env python3
"""Apply a conservative AllDup-inspired classic layout to Krokiet's Slint UI.

Preserves the original ActionButtons instance and Rust callbacks. Repeat-safe.
Only touches UI files after checking every required anchor.
"""
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
mw = root / 'krokiet/ui/main_window.slint'
table = root / 'krokiet/ui/components/selectable_tree_view.slint'
for path in (mw, table):
    if not path.is_file():
        sys.exit(f'ERROR: Missing {path}. Pass the Czkawka checkout as the argument.')

main = mw.read_text(encoding='utf-8')
tree = table.read_text(encoding='utf-8')
if 'Classic Krokiet toolbar' in main:
    print('Classic layout already applied; no changes needed.')
    sys.exit(0)

def once(content, old, new, name):
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f'{name}: expected one occurrence, found {count}; upstream layout changed. Nothing written.')
    return content.replace(old, new, 1)

# Keep toolbar definitions and callbacks byte-for-byte intact; move existing instance.
start_token = '        action_buttons := ActionButtons {'
end_token = '        HorizontalLayout {\n            spacing: 5px;\n            text_summary := LineEdit {'
start = main.find(start_token)
end = main.find(end_token, start)
if start == -1 or end == -1 or start >= end:
    raise RuntimeError('Original action bar/status boundary not found. Nothing written.')
buttons = main[start:end]
if buttons.count('action_buttons := ActionButtons {') != 1:
    raise RuntimeError('Unexpected action bar structure. Nothing written.')
main = main[:start] + main[end:]

main = once(main, '''    min-width: 300px;
    preferred-width: 800px;
    min-height: 300px;
    preferred-height: 600px;''', '''    min-width: 850px;
    preferred-width: 1360px;
    min-height: 520px;
    preferred-height: 820px;''', 'window size')

main = once(main, '''    VerticalBox {
        HorizontalBox {
            vertical-stretch: 1.0;''', '''    VerticalBox {
        spacing: 2px;
        // Classic Krokiet toolbar: keeps all existing actions and popup callbacks.
        Rectangle {
            height: 26px;
            background: #e7eaf0;
            border-color: #afb7c2;
            border-width: 1px;
            HorizontalLayout {
                padding-left: 10px;
                padding-right: 10px;
                Text {
                    text: "KROKIET  /  DUPLICATE FILE SEARCH";
                    font-size: 12px;
                    font-weight: 700;
                    color: #273e56;
                    vertical-alignment: center;
                }
                Rectangle { horizontal-stretch: 1; background: transparent; }
                Text {
                    text: "Select files below, then use the actions toolbar";
                    font-size: 11px;
                    color: #526477;
                    vertical-alignment: center;
                }
            }
        }
''' + buttons + '''        HorizontalBox {
            vertical-stretch: 1.0;''', 'top toolbar position')
main = once(main, 'width: preview_or_tool_settings.visible ? parent.width / 2 : parent.width;', 'width: preview_or_tool_settings.visible ? parent.width * 0.70 : parent.width;', 'result width')
main = once(main, '''                        x: parent.width / 2;
                        width: self.visible ? parent.width / 2 : 0;''', '''                        x: parent.width * 0.70;
                        width: self.visible ? parent.width * 0.30 : 0;''', 'preview width')
# Keep status LineEdit callbacks intact; just add a classic background using a plain rectangular border around summary is intentionally omitted.

tree = once(tree, 'out property <length> item_height: 23px;', 'out property <length> item_height: 21px;', 'row height')
tree = once(tree, '''        ScrollView {
            height: 30px;''', '''        ScrollView {
            height: 26px;''', 'column header height')
tree = once(tree, '''                spacing: 5px;
                for title[idx] in root.columns:''', '''                spacing: 2px;
                for title[idx] in root.columns:''', 'header spacing')
tree = once(tree, '''                        width: 1px;
                        background: gray;''', '''                        width: 1px;
                        background: #a8b2bf;''', 'column separators')
tree = once(tree, '''                border-radius: 5px;
                height: item_height;
                background: ColorPalette.get_listview_color_with_header(r.focused_row, touch-area.has-hover, r.header_row);''', '''                border-radius: 0px;
                height: item_height;
                background: r.header_row ? #dae5f0 : (r.focused_row ? #bed8f3 : (touch-area.has-hover ? #eaf3fb : (Math.mod(idx, 2) == 0 ? #ffffff : #f5f7f9)));''', 'table row styling')

# Atomic writes only after successful checks. Backups are in the checkout for easy rollback.
for path, content in ((mw, main), (table, tree)):
    backup = path.with_suffix(path.suffix + '.before-classic')
    if not backup.exists():
        backup.write_bytes(path.read_bytes())
    path.write_text(content, encoding='utf-8')
print('Applied conservative Classic Krokiet layout:')
print(' - Original toolbar moved above results; callbacks unchanged')
print(' - 70/30 results-to-preview split')
print(' - Dense 21px table rows, compact headers and alternating row backgrounds')
print(' - Original source backups created with .before-classic suffix')
