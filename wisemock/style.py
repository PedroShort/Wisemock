"""Qt stylesheet for the WiseMock app."""

STYLE = """
/* ── WISEflow-inspired theme ─────────────────────────── */
QMainWindow, QWidget {
    background: #e8e8e8; color: #333333;
    font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif; font-size: 14px;
}
QScrollArea { border: none; background: #e8e8e8; }
QLabel { background: transparent; }

#PageCard { background: #ffffff; border: 1px solid #d5d5d5; border-radius: 3px; }
#SectionTitle { font-size: 24px; font-weight: 600; color: #333333; }
#BodyText { font-size: 14px; color: #444444; }
#CodeBlock {
    background: #f7f7f7; border: 1px solid #dcdcdc; border-radius: 3px;
    padding: 14px; font-family: Consolas, "Courier New", monospace; font-size: 13px; color: #333333;
}
#QuestionTitle { font-size: 15px; font-weight: 600; color: #333333; margin-top: 8px; margin-bottom: 4px; }
#OptionCard { background: #ffffff; border: 1px solid #d5d5d5; border-radius: 3px; }
#OptionCardSelected { background: #fef9e7; border: 1px solid #d4ac0d; border-left: 4px solid #d4ac0d; border-radius: 3px; }
#LetterBox {
    min-width: 42px; max-width: 42px; min-height: 42px; background: transparent;
    font-size: 20px; color: #555555; qproperty-alignment: 'AlignCenter';
}
#OptionTextBox {
    background: #fafafa; border: 1px solid #e0e0e0; border-radius: 3px; padding: 10px 12px;
    font-family: Consolas, "Courier New", monospace; font-size: 13px; color: #444444;
}
QPushButton { text-align: left; border: none; background: transparent; padding: 0px; }
QPushButton:hover { background: transparent; }
#OpenEndedBox { background: #ffffff; border: 1px solid #d5d5d5; border-radius: 3px; padding: 10px; font-size: 14px; color: #333333; }
#PrimaryButton { background: #4a4a4a; color: white; border-radius: 3px; padding: 10px 20px; font-weight: 600; text-align: center; }
#PrimaryButton:hover { background: #333333; }
#DangerButton { background: #c0392b; color: white; border-radius: 3px; padding: 10px 20px; font-weight: 600; text-align: center; }
#DangerButton:hover { background: #a93226; }
#TimerBox {
    background: #ffffff; border: 1px solid #d5d5d5; border-radius: 3px; padding: 10px 18px;
    font-size: 15px; font-weight: 600; color: #333333; min-width: 200px;
}
#TimeUpBanner { background: #fdeaea; border: 1px solid #e6b3b3; border-radius: 3px; padding: 10px 14px; color: #922b21; font-size: 14px; font-weight: 600; }
#ScoreBanner { background: #f0f0f0; border: 1px solid #d0d0d0; border-left: 4px solid #3c3c3c; border-radius: 3px; padding: 10px 14px; color: #333333; font-size: 14px; font-weight: 600; }
#OptionCardCorrect { background: #eafaf1; border: 1px solid #82d8a0; border-left: 4px solid #27ae60; border-radius: 3px; }
#OptionCardWrong { background: #fdeaea; border: 1px solid #e6a5a5; border-left: 4px solid #c0392b; border-radius: 3px; }

#SuggestedAnswerBox { background: #eafaf1; border: 1px solid #a9dfbf; border-left: 4px solid #27ae60; border-radius: 3px; padding: 10px 12px; font-size: 13px; color: #1e6a3f; }
#AIButton { background: #5b5b5b; color: white; border-radius: 3px; padding: 8px 16px; font-weight: 600; font-size: 13px; text-align: center; }
#AIButton:hover { background: #444444; }
#AIButton:disabled { background: #c0c0c0; color: #e8e8e8; }
#AIFeedbackBox { background: #f4f0fa; border: 1px solid #c5b3e0; border-left: 4px solid #7d3cad; border-radius: 3px; padding: 10px 12px; font-size: 13px; color: #4a1a7a; }

#FillBlankTemplate {
    background: #f7f7f7; border: 1px solid #dcdcdc; border-radius: 3px; padding: 14px;
    font-family: Consolas, "Courier New", monospace; font-size: 13px; color: #333333;
}
QComboBox { background: #ffffff; border: 1px solid #cccccc; border-radius: 3px; padding: 5px 10px; font-size: 13px; color: #333333; min-height: 28px; }
QComboBox:focus { border: 1px solid #4a90c4; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: #ffffff; border: 1px solid #cccccc; selection-background-color: #4a4a4a; selection-color: white; font-size: 13px; }

#SetupRoot { background: #dcdcdc; }
#SetupHeader { background: #3c3c3c; }
#AppTitle { font-size: 15px; font-weight: 600; color: #f2f2f2; letter-spacing: -0.2px; }
#AppTagline { font-size: 10px; color: #888888; letter-spacing: 0px; }
#SetupCard { background: #ffffff; border: 1px solid #e8e8e8; border-radius: 4px; }
#DropZone { background: transparent; border: 2px dashed transparent; border-radius: 12px; }
#DropZoneHover { background: #f7f7f7; border: 2px dashed #d0d0d0; border-radius: 12px; }
#DropZoneLoaded { background: transparent; border: 2px solid transparent; border-radius: 12px; }
#DropMainText { font-size: 15px; font-weight: 600; color: #1a1a1a; }
#DropSubText { font-size: 13px; color: #aaaaaa; }
#FileNameLabel { font-size: 15px; font-weight: 600; color: #1e8449; }
#FileMetaLabel { font-size: 13px; color: #777777; }
#SectionDivider { background: #e8e8e8; max-height: 1px; min-height: 1px; }
#SettingGroupLabel { font-size: 11px; font-weight: 700; color: #aaaaaa; letter-spacing: 1.5px; }
#StartButton { background: #2c2c2c; color: #ffffff; border-radius: 12px; padding: 15px 72px; font-size: 16px; font-weight: 600; text-align: center; }
#StartButton:hover { background: #1a1a1a; }
#StartButton:disabled { background: #c8c8c8; color: #999999; }
#SecondaryButton { background: transparent; color: #4a4a4a; border: 1px solid #999999; border-radius: 3px; padding: 6px 18px; font-size: 13px; text-align: center; }
#SecondaryButton:hover { background: #f0f0f0; border-color: #4a4a4a; }

QFrame#DropCard {
    background-color: #ffffff; border: 1px solid #e8e8e8;
    border-top-left-radius: 14px; border-top-right-radius: 14px;
    border-bottom-left-radius: 0px; border-bottom-right-radius: 0px;
    border-bottom: none;
}
QFrame#SettingsCard {
    background-color: #ffffff; border: 1px solid #e8e8e8; border-top: none;
}
QFrame#BottomCard {
    background-color: #ffffff; border: 1px solid #e8e8e8; border-top: none;
    border-top-left-radius: 0px; border-top-right-radius: 0px;
    border-bottom-left-radius: 14px; border-bottom-right-radius: 14px;
}

QTabWidget::pane { border: none; border-top: 1px solid #b8b8b8; background: #dcdcdc; }
QTabWidget { background: #cacaca; }
QTabBar { background: #cacaca; qproperty-drawBase: 0; }
QTabBar::tab { background: transparent; color: #777777; padding: 14px 28px; border: none; border-bottom: 2px solid transparent; font-size: 13px; font-weight: 500; margin-right: 0px; }
QTabBar::tab:selected { background: transparent; color: #1a1a1a; border-bottom: 2px solid #1a1a1a; }
QTabBar::tab:hover:!selected { color: #444444; }

QLineEdit { background: #f7f7f7; border: 1px solid #d0d0d0; border-radius: 8px; padding: 9px 14px; font-size: 15px; color: #1a1a1a; }
QLineEdit:focus { border: 1px solid #999999; background: #ffffff; }
QSpinBox { background: #ffffff; border: 1px solid #cccccc; border-radius: 3px; padding: 5px 8px; font-size: 13px; color: #333333; min-width: 64px; }
QCheckBox { font-size: 13px; color: #444444; spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #bbbbbb; border-radius: 2px; background: #ffffff; }
QCheckBox::indicator:checked { background: #4a4a4a; border: 1px solid #4a4a4a; }
QCheckBox:disabled { color: #bbbbbb; }
#GuideTitle { font-size: 18px; font-weight: 600; color: #333333; }
#GuideSubtitle { font-size: 13px; color: #777777; }

#StatCard { background: #ffffff; border: 1px solid #d5d5d5; border-radius: 4px; padding: 16px; }
#StatValue { font-size: 28px; font-weight: 700; color: #333333; }
#StatLabel { font-size: 10px; color: #999999; letter-spacing: 1px; }
#HistoryTable { background: #ffffff; border: 1px solid #d5d5d5; border-radius: 3px; font-size: 13px; gridline-color: #eeeeee; }
#HistoryTable::item { padding: 6px 10px; }
QHeaderView::section { background: #f5f5f5; border: none; border-bottom: 1px solid #d5d5d5; font-size: 11px; font-weight: 700; color: #777777; padding: 8px 10px; letter-spacing: 0.5px; }
#EmptyHistory { font-size: 14px; color: #aaaaaa; }
"""
