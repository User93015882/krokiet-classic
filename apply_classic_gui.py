#!/usr/bin/env python3
"""Apply Classic AllDup-style UI changes to a Czkawka/Krokiet source checkout.
Does not modify Rust business logic. Run from the repository root.
"""
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv)>1 else '.').resolve()
ui = root/'krokiet'/'ui'
assert (ui/'main_window.slint').exists(), 'Expected krokiet/ui/main_window.slint in the checkout'

def replace(path, old, new, count=1):
    s=path.read_text(encoding='utf-8')
    n=s.count(old)
    if n != count:
        raise RuntimeError(f'{path}: expected {count} matches, got {n}: {old[:80]!r}. Check upstream revision.')
    path.write_text(s.replace(old,new), encoding='utf-8')

mw=ui/'main_window.slint'
replace(mw, 'import { HorizontalBox, LineEdit, Palette, VerticalBox } from "std-widgets.slint";', 'import { HorizontalBox, LineEdit, Palette, VerticalBox, Button } from "std-widgets.slint";')
replace(mw, '''    min-width: 300px;
    preferred-width: 800px;
    min-height: 300px;
    preferred-height: 600px;''', '''    min-width: 960px;
    preferred-width: 1440px;
    min-height: 600px;
    preferred-height: 850px;''')
replace(mw, '''    VerticalBox {
        HorizontalBox {
            vertical-stretch: 1.0;''', '''    VerticalBox {
        spacing: 0px;
        // Traditional menu strip. Commands reuse the existing callbacks and popup paths.
        Rectangle {
            height: 29px;
            background: #f0f0f0;
            border-color: #c8c8c8;
            border-width: 1px;
            HorizontalLayout {
                padding-left: 8px;
                spacing: 1px;
                Button { text: "Search"; clicked => { action_buttons.bottom_panel_visibility = BottomPanelVisibility.Directories; } }
                Button { text: "Search options"; clicked => { GuiState.visible_tool_settings = !GuiState.visible_tool_settings; } }
                Button { text: "Results"; clicked => { GuiState.preview_visible = false; } }
                Button { text: "Preview"; clicked => { GuiState.preview_visible = !GuiState.preview_visible; } }
                Rectangle { horizontal-stretch: 1; background: transparent; }
                Text { text: "Krokiet  |  Classic workspace"; color: #555555; vertical-alignment: center; }
                Rectangle { width: 12px; background: transparent; }
            }
        }
        // Existing action controls (scan, stop, select, move, delete, trash,
        // save and sort) form a compact functional toolbar above the results.
        Rectangle {
            height: 39px;
            background: #eeeeee;
            border-color: #cbcbcb;
            border-width: 1px;
            action_buttons := ActionButtons {
                x: 7px;
                y: 4px;
                width: parent.width - 14px;
                duplicate_files_model <=> root.duplicate_files_model;
                empty_folder_model <=> root.empty_folder_model;
                big_files_model <=> root.big_files_model;
                empty_files_model <=> root.empty_files_model;
                temporary_files_model <=> root.temporary_files_model;
                similar_images_model <=> root.similar_images_model;
                similar_videos_model <=> root.similar_videos_model;
                similar_music_model <=> root.similar_music_model;
                invalid_symlinks_model <=> root.invalid_symlinks_model;
                broken_files_model <=> root.broken_files_model;
                bad_extensions_model <=> root.bad_extensions_model;
                bad_names_model <=> root.bad_names_model;
                exif_remover_model <=> root.exif_remover_model;
                video_optimizer_model <=> root.video_optimizer_model;
                scanning <=> root.scanning;
                processing <=> root.processing;
                stop_requested <=> root.stop_requested;
                scan_stopping => { text_summary_text = Translations.stopping_scan_text; root.scan_stopping(); }
                scan_starting(item) => {
                    text_summary_text = Translations.searching_text;
                    root.scan_starting(item);
                    main_list.scan_started();
                }
                show_select_popup(x_offset, y_offset) => {
                    select_popup_window.x_offset = x_offset;
                    select_popup_window.y_offset = y_offset;
                    select_popup_window.show_popup();
                }
                show_action_popup(popup_request) => { request_setup_action_popup(popup_request); }
                show_sort_popup(x_offset, y_offset) => {
                    sort_popup_window.x_offset = x_offset;
                    sort_popup_window.y_offset = y_offset;
                    sort_popup_window.show_popup();
                }
            }
        }
        Rectangle {
            height: 27px;
            background: #dce6f1;
            border-color: #b3c6dc;
            border-width: 1px;
            HorizontalLayout {
                padding-left: 10px;
                padding-right: 10px;
                spacing: 10px;
                Text { text: "SEARCH RESULTS"; color: #1d3b58; font-size: 12px; font-weight: 700; vertical-alignment: center; }
                Rectangle { horizontal-stretch: 1; background: transparent; }
                Text { text: "Tick files to select  •  Double-click to open  •  Click a column to sort"; font-size: 11px; color: #405d76; vertical-alignment: center; }
            }
        }
        HorizontalBox {
            vertical-stretch: 1.0;''')
# Add enum import only if not already present
replace(mw, 'import { ActiveTab, PopupRequest, ProgressToSend, SingleMainListModel } from "globals/common.slint";', 'import { ActiveTab, BottomPanelVisibility, PopupRequest, ProgressToSend, SingleMainListModel } from "globals/common.slint";')
replace(mw, 'width: preview_or_tool_settings.visible ? parent.width / 2 : parent.width;', 'width: preview_or_tool_settings.visible ? parent.width * 0.72 : parent.width;')
replace(mw, '''                        x: parent.width / 2;
                        width: self.visible ? parent.width / 2 : 0;''', '''                        x: parent.width * 0.72;
                        width: self.visible ? parent.width * 0.28 : 0;''')
# Remove the previous footer ActionButtons block without touching toolbar's own actions.
s=mw.read_text(encoding='utf-8')
start=s.find('        action_buttons := ActionButtons {',s.find('        HorizontalBox {\n            vertical-stretch: 1.0;'))
stop=s.find('        HorizontalLayout {\n            spacing: 5px;\n            text_summary',start)
if start<0 or stop<0: raise RuntimeError('Could not locate original bottom ActionButtons block')
s=s[:start]+s[stop:]
mw.write_text(s,encoding='utf-8')
replace(mw, '''        HorizontalLayout {
            spacing: 5px;
            text_summary := LineEdit {''', '''        Rectangle {
            height: 31px;
            background: #ededed;
            border-color: #c0c0c0;
            border-width: 1px;
            HorizontalLayout {
                padding-left: 8px;
                padding-right: 8px;
                spacing: 12px;
                Text {
                    text: root.scanning ? (root.stop_requested ? "Stopping" : "Scanning") : (root.processing ? "Processing" : "Ready");
                    width: 82px;
                    color: root.scanning ? #124f80 : #333333;
                    vertical-alignment: center;
                }
                text_summary := LineEdit {''')
replace(mw, '''                font-size: FontSizes.normal;
            }

            Text {
                font-size: FontSizes.normal;
                text: "Krokiet\\n12.0.2";
                vertical-alignment: center;
                horizontal-alignment: center;
            }
        }
        bottom_panel''','''                font-size: FontSizes.normal;
                horizontal-stretch: 1;
                }
                Text { text: "Krokiet"; color: #555555; vertical-alignment: center; }
            }
        }
        bottom_panel''')

# Classic dense list/table chrome, retaining Slint model binding, group headers,
# checkbox semantics and Rust-backed sorting.
table=ui/'components'/'selectable_tree_view.slint'
replace(table, 'out property <length> item_height: 23px;', 'out property <length> item_height: 21px;')
replace(table, '''        ScrollView {
            height: 30px;''', '''        ScrollView {
            height: 26px;''')
replace(table, '''                spacing: 5px;
                for title[idx] in root.columns:''', '''                spacing: 1px;
                for title[idx] in root.columns:''')
replace(table, '''                    Rectangle {
                        width: 1px;
                        background: gray;''', '''                    Rectangle {
                        width: 1px;
                        background: #a9b5c0;''')
replace(table, '''                border-radius: 5px;
                height: item_height;
                background: ColorPalette.get_listview_color_with_header(r.focused_row, touch-area.has-hover, r.header_row);''', '''                border-radius: 0px;
                height: item_height;
                background: r.header_row ? #dce7f3 : (r.focused_row ? #bcd9f4 : (touch-area.has-hover ? #edf5fe : (idx % 2 == 0 ? #ffffff : #f6f6f6)));''')
replace(table, '''                    Rectangle {
                        width: 5px;
                    }
                    // Workaround''', '''                    Rectangle {
                        width: 3px;
                    }
                    // Workaround''')

print('Applied classic layout to:')
print(' ',mw)
print(' ',table)
print('Build on Windows using the repository instructions and test scanning/selection/deletion.')
