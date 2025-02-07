D_STYLE_SHEET = """
/* ==========================================================================================
 * PyQtDarkTheme.
 *
 *  This is originally a fork of QDarkStyleSheet distributed under the terms of the MIT License.
 *   see https://github.com/ColinDuquesnoy/QDarkStyleSheet/blob/master/LICENSE.rst#the-mit-license-mit---code
 *
 * Original code:
 *   https://github.com/ColinDuquesnoy/QDarkStyleSheet/blob/master/qdarkstyle/dark/style.qss
 *
 * -------------------------------------------------------------------------------------------
 * The MIT License (MIT)
 *
 * Copyright (c) 2013-2014 Colin Duquesnoy
 * Copyright (c) 2021-2022 Yunosuke Ohsugi
 * ==========================================================================================
 */
* {
    padding: 0px;
    margin: 0px;
    border: 0px;
    border-style: none;
    border-image: none;
    outline: 0;
}
QToolBar * {
    margin: 0px;
    padding: 0px;
}
QWidget {
    background-color: rgba(32.000, 33.000, 36.000, 1.000);
    color: rgba(170.000, 170.000, 170.000, 1.000);
    selection-background-color: rgba(138.000, 180.000, 247.000, 1.000);
    selection-color: rgba(32.000, 33.000, 36.000, 1.000);
}
QWidget:disabled {
    color: rgba(105.000, 113.000, 119.000, 1.000);
    selection-background-color: rgba(83.000, 87.000, 91.000, 1.000);
    selection-color: rgba(105.000, 113.000, 119.000, 1.000);
}
QWidget {
    backward-icon: url(${path}/dark/svg/arrow_upward__icon-foreground__rotate-270.svg);
    forward-icon: url(${path}/dark/svg/arrow_upward__icon-foreground__rotate-90.svg);
    leftarrow-icon: url(${path}/dark/svg/arrow_upward__icon-foreground__rotate-270.svg);
    rightarrow-icon: url(${path}/dark/svg/arrow_upward__icon-foreground__rotate-90.svg);
    dialog-ok-icon: url(${path}/dark/svg/check__icon-foreground.svg);
    dialog-cancel-icon: url(${path}/dark/svg/close__icon-foreground.svg);
    dialog-yes-icon: url(${path}/dark/svg/check_circle__icon-foreground.svg);
    dialog-no-icon: url(${path}/dark/svg/cancel__icon-foreground.svg);
    dialog-apply-icon: url(${path}/dark/svg/check__icon-foreground.svg);
    dialog-reset-icon: url(${path}/dark/svg/restart_alt__icon-foreground.svg);
    dialog-save-icon: url(${path}/dark/svg/save__icon-foreground.svg);
    dialog-discard-icon: url(${path}/dark/svg/delete__icon-foreground.svg);
    dialog-close-icon: url(${path}/dark/svg/close__icon-foreground.svg);
    dialog-open-icon: url(${path}/dark/svg/folder_open__icon-foreground.svg);
    dialog-help-icon: url(${path}/dark/svg/help__icon-foreground.svg);
    filedialog-parent-directory-icon: url(${path}/dark/svg/arrow_upward__icon-foreground.svg);
    filedialog-new-directory-icon: url(${path}/dark/svg/create_new_folder__icon-foreground.svg);
    titlebar-close-icon: url(${path}/dark/svg/close__icon-foreground.svg);
    titlebar-normal-icon: url(${path}/dark/svg/flip_to_front__icon-foreground.svg);
}
QCommandLinkButton {
    qproperty-icon: url(${path}/dark/svg/east__highlight.svg);
}
QMainWindow::separator {
    width: 2px;
    height: 4px;
    background-color: rgba(63.000, 64.000, 66.000, 1.000);
}
QMainWindow::separator:hover,
QMainWindow::separator:pressed {
    background-color: rgba(138.000, 180.000, 247.000, 1.000);
}
QToolTip {
    background-color: rgba(41.000, 42.000, 45.000, 1.000);
    color: rgba(228.000, 231.000, 235.000, 1.000);
    border: 1px solid rgba(63.000, 64.000, 66.000, 1.000);
}
QSizeGrip {
    width: 0;
    height: 0;
    image: none;
}
QStatusBar {
    background-color: rgba(42.000, 43.000, 46.000, 1.000);
}
QStatusBar::item {
    border: none;
}
QStatusBar QWidget {
    background-color: transparent;
    padding: 0px;
    border-radius: 0px;
    margin: 0px;
}
QStatusBar QWidget:pressed {
    background-color: rgba(79.000, 80.000, 84.000, 1.000);
}
QStatusBar QWidget:disabled {
    background-color: rgba(32.000, 33.000, 36.000, 1.000);
}
QStatusBar QWidget:checked {
    background-color: rgba(79.000, 80.000, 84.000, 1.000);
}
QCheckBox,
QRadioButton {
    border-width: 2px 0;
    border-style: solid;
    border-color: transparent;
}
QCheckBox:hover,
QRadioButton:hover {
    border-bottom: 2px solid rgba(138.000, 180.000, 247.000, 1.000);
}
QCheckBox::indicator,
QRadioButton::indicator {
    margin: 0 0 2 0;
    height: 18px;
    width: 18px;
}
QRadioButton {
    spacing: 8px;
}
QRadioButton::indicator:unchecked {
    image: url(${path}/dark/svg/radio_button_unchecked__icon-foreground.svg);
}
QRadioButton::indicator:unchecked:disabled {
    image: url(${path}/dark/svg/radio_button_unchecked__icon-foreground-disabled.svg);
}
QRadioButton::indicator:checked {
    image: url(${path}/dark/svg/radio_button_checked__highlight.svg);
}
QRadioButton::indicator:checked:disabled {
    image: url(${path}/dark/svg/radio_button_checked__icon-foreground-disabled.svg);
}
QGroupBox {
    font-weight: bold;
    border: 1px solid rgba(63.000, 64.000, 66.000, 1.000);
    border-radius: 4px;
    padding: 2px;
    margin: 9px 0 4px 0;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 7px;
    top: 2px;
    spacing: 6px;
    margin: 0 2px 0 2px;
}
QMenuBar {
    background-color: rgba(32.000, 33.000, 36.000, 1.000);
    padding: 2px;
}
QMenuBar::item {
    background: transparent;
    padding: 4px;
}
QMenuBar::item:selected {
    padding: 4px;
    background-color: rgba(68.000, 70.000, 77.000, 1.000);
    border-radius: 4px;
}
QMenuBar::item:pressed {
    padding: 4px;
    margin-bottom: 0px;
    padding-bottom: 0px;
}
QToolBar {
    background-color: rgba(41.000, 42.000, 45.000, 1.000);
    padding: 1x;
    font-weight: bold;
    spacing: 1px;
    margin: 1px;
}
QToolBar::handle:horizontal {
    width: 10px;
    image: url(${path}/dark/svg/drag_indicator_horizontal__icon-foreground.svg);
}
QToolBar::handle:vertical {
    height: 20px;
    image: url(${path}/dark/svg/drag_indicator_horizontal__icon-foreground__rotate-90.svg);
}
QToolBar::separator {
    background-color: rgba(63.000, 64.000, 66.000, 1.000);
}
QToolBar::separator:horizontal {
    width: 2px;
    margin: 0 6px;
}
QToolBar::separator:vertical {
    height: 2px;
    margin: 6px 0;
}
QToolBar > QToolButton {
    background-color: transparent;
    padding: 0px;
    border-radius: 0px;
}
QToolBar > QToolButton:hover {
    background-color: rgba(68.000, 70.000, 74.000, 1.000);
}
QToolBar > QToolButton:pressed {
    background-color: rgba(79.000, 80.000, 84.000, 1.000);
}
QToolBar > QToolButton:checked {
    background-color: rgba(79.000, 80.000, 84.000, 1.000);
}
QToolBar > QToolButton#qt_toolbar_ext_button {
    image: url(${path}/dark/svg/double_arrow__icon-foreground.svg);
}
QToolBar > QToolButton#qt_toolbar_ext_button:disabled {
    image: url(${path}/dark/svg/double_arrow__icon-foreground-disabled.svg);
}
QMenu {
    background-color: rgba(41.000, 42.000, 45.000, 1.000);
    padding: 8px 0;
    border: 1px solid rgba(63.000, 64.000, 66.000, 1.000);
}
QMenu::separator {
    height: 1px;
    background-color: rgba(63.000, 64.000, 66.000, 1.000);
}
QMenu::item {
    padding: 4px 28px;
}
QMenu::item:selected {
    background-color: rgba(63.000, 64.000, 66.000, 1.000);
}
QMenu::icon {
    padding-left: 10px;
    width: 14px;
    height: 14px;
}
QMenu::right-arrow {
    margin: 2px;
    padding-left: 12px;
    height: 20px;
    width: 20px;
    image: url(${path}/dark/svg/chevron_right__icon-foreground.svg);
}
QMenu::right-arrow:disabled {
    image: url(${path}/dark/svg/chevron_right__icon-foreground-disabled.svg);
}
QScrollBar {
    background-color: transparent;
}
QScrollBar:horizontal {
    height: 7px;
}
QScrollBar:vertical {
    width: 7px;
}
QScrollBar::handle {
    background-color: rgba(84.000, 86.000, 86.000, 0.737);
    border-radius: 3px;
}
QScrollBar::handle:hover {
    background-color: rgba(114.000, 115.000, 115.000, 0.827);
}
QScrollBar::handle:pressed {
    background-color: rgba(143.000, 145.000, 145.000, 0.933);
}
QScrollBar::handle:horizontal {
    min-width: 8px;
}
QScrollBar::handle:vertical {
    min-height: 8px;
}
QScrollBar::sub-line, QScrollBar::add-line {
    width: 0;
    height: 0;
}
QScrollBar::sub-page, QScrollBar::add-page {
    background-color: transparent;
}
QProgressBar {
    border: 1px solid rgba(63.000, 64.000, 66.000, 1.000);
    border-radius: 4px;
    text-align: center;
    color: rgba(228.000, 231.000, 235.000, 1.000);
}
QProgressBar::chunk {
    background-color: rgba(138.000, 180.000, 247.000, 1.000);
    border-radius: 3px;
}
QProgressBar::chunk:disabled {
    background-color: rgba(83.000, 87.000, 91.000, 1.000);
}
QPushButton {
    border: 1px solid rgba(63.000, 64.000, 66.000, 1.000);
    padding: 4px 8px;
    border-radius: 4px;
    color: rgba(138.000, 180.000, 247.000, 1.000);
}
QPushButton:hover {
    background-color: rgba(30.000, 43.000, 60.000, 1.000);
}
QPushButton:pressed {
    background-color: rgba(46.000, 70.000, 94.000, 1.000);
}
QPushButton:checked {
    border-color: rgba(138.000, 180.000, 247.000, 1.000);
}
QPushButton:disabled {
    border-color: rgba(63.000, 64.000, 66.000, 1.000);
}
QPushButton[flat=true]:!checked {
    border-color: transparent;
}
QDialogButtonBox QPushButton {
    min-width: 65px;
}
QToolButton {
    border: 1px solid rgba(63.000, 64.000, 66.000, 1.000);
    padding: 5px;
    border-radius: 2px;
    spacing: 2px;
}
QToolButton:hover {
    background-color: rgba(30.000, 43.000, 60.000, 1.000);
}
QToolButton:pressed {
    background-color: rgba(46.000, 70.000, 94.000, 1.000);
}
QToolButton:selected,
QToolButton:checked {
    background-color: rgba(46.000, 70.000, 94.000, 1.000);
}
QToolButton::checked:disabled {
    background-color: rgba(63.000, 64.000, 66.000, 1.000);
}
QToolButton::menu-button {
    padding: 1px;
    border-radius: 4px;
    width: 12px;
}
QToolButton::menu-button {
    border: 1px solid transparent;
}
QToolButton::menu-button:hover, QToolButton::menu-button:checked:hover {
    border-color: rgba(138.000, 180.000, 247.000, 1.000);
}
QToolButton::menu-indicator {
    height: 18px;
    width: 18px;
    top: 6px;
    left: 3px;
    image: url(${path}/dark/svg/expand_less__icon-foreground__rotate-180.svg);
}
QToolButton::menu-indicator:disabled {
    image: url(${path}/dark/svg/expand_less__icon-foreground-disabled__rotate-180.svg);
}
QToolButton::menu-arrow {
    height: 8px;
    width: 8px;
}
QToolButton[popupMode="1"] {
    padding-right: 14px;
}
QComboBox {
    border: 1px solid rgba(63.000, 64.000, 66.000, 1.000);
    border-radius: 4px;
    min-height: 1.5em;
    padding: 0 4px;
    background-color: rgba(63.000, 64.000, 66.000, 1.000);
}
QComboBox:focus,
QComboBox:open {
    border: 1px solid rgba(138.000, 180.000, 247.000, 1.000);
}
QComboBox::drop-down {
    subcontrol-position: center right;
    border: none;
    padding-right: 4px;
}
QComboBox::down-arrow {
    height: 23px;
    width: 23px;
    image: url(${path}/dark/svg/expand_less__icon-foreground__rotate-180.svg);
}
QComboBox::down-arrow:disabled {
    image: url(${path}/dark/svg/expand_less__icon-foreground-disabled__rotate-180.svg);
}
QComboBox::item:selected {
    border: none;
    background-color: rgba(0.000, 72.000, 117.000, 1.000);
    color: rgba(228.000, 231.000, 235.000, 1.000);
}
QComboBox QAbstractItemView {
    margin: 0;
    border: 1px solid rgba(63.000, 64.000, 66.000, 1.000);
    selection-background-color: rgba(0.000, 72.000, 117.000, 1.000);
    selection-color: rgba(228.000, 231.000, 235.000, 1.000);
    padding: 2px;
}
QSlider {
    padding: 2px 0;
}
QSlider:focus {
    border: none;
}
QSlider::groove {
    border-radius: 2px;
}
QSlider::groove:horizontal {
    height: 4px;
}
QSlider::groove:vertical {
    width: 4px;
}
QSlider::sub-page, QSlider::handle {
    background-color: rgba(138.000, 180.000, 247.000, 1.000);
}
QSlider::sub-page:disabled,
QSlider::add-page:disabled,
QSlider::handle:disabled {
    background-color: rgba(83.000, 87.000, 91.000, 1.000);
}
QSlider::add-page {
    background-color: rgba(54.000, 86.000, 140.000, 1.000);
}
QSlider::handle:hover {
    background-color: rgba(127.000, 166.000, 228.000, 1.000);
}
QSlider::handle:horizontal {
    width: 16px;
    height: 8px;
    margin: -6px 0;
    border-radius: 8px;
}
QSlider::handle:vertical {
    width: 8px;
    height: 16px;
    margin: 0 -6px;
    border-radius: 8px;
}
QTabWidget::pane {
    border: 1px solid rgba(63.000, 64.000, 66.000, 1.000);
    border-radius: 3px;
}
QTabBar {
    qproperty-drawBase: 0;
}
QTabBar::close-button:selected {
    image: url(${path}/dark/svg/close__icon-foreground.svg);
}
QTabBar::close-button:!selected {
    image: url(${path}/dark/svg/close__tabbar-button-inselected.svg)
}
QTabBar::close-button:disabled {
    image: url(${path}/dark/svg/close__icon-foreground-disabled.svg);
}
QTabBar::close-button:hover {
    background-color: rgba(85.000, 128.000, 173.000, 1.000);
    border-radius: 4px
}
QTabBar::close-button:hover:!selected {
    background-color: rgba(50.000, 71.000, 99.000, 1.000);
}
QTabBar::tab {
    padding: 3px;
}
QTabBar::tab:hover {
    background-color: rgba(30.000, 43.000, 60.000, 1.000);
}
QTabBar::tab:selected {
    color: rgba(138.000, 180.000, 247.000, 1.000);
    background-color: rgba(46.000, 70.000, 94.000, 1.000);
}
QTabBar::tab:selected:disabled {
    background-color: rgba(83.000, 87.000, 91.000, 1.000);
    color: rgba(105.000, 113.000, 119.000, 1.000);
}
QTabBar::tab:top {
    border-top-left-radius: 2px;
    border-top-right-radius: 2px;
    border-bottom: 2px solid rgba(63.000, 64.000, 66.000, 1.000);
    margin-left: 4px;
}
QTabBar::tab:top:selected {
    border-bottom: 2px solid rgba(138.000, 180.000, 247.000, 1.000);
}
QTabBar::tab:top:hover {
    border-color: rgba(138.000, 180.000, 247.000, 1.000);
}
QTabBar::tab:top:selected:disabled {
    border-color: rgba(83.000, 87.000, 91.000, 1.000);
}
QTabBar::tab:bottom {
    border-bottom-left-radius: 2px;
    border-bottom-right-radius: 2px;
    border-top: 2px solid rgba(63.000, 64.000, 66.000, 1.000);
    margin-left: 4px;
}
QTabBar::tab:bottom:selected {
    border-top: 2px solid rgba(138.000, 180.000, 247.000, 1.000);
}
QTabBar::tab:bottom:hover {
    border-color: rgba(138.000, 180.000, 247.000, 1.000);
}
QTabBar::tab:bottom:selected:disabled {
    border-color: rgba(83.000, 87.000, 91.000, 1.000);
}
QTabBar::tab:left {
    border-top-left-radius: 2px;
    border-bottom-left-radius: 2px;
    border-right: 2px solid rgba(63.000, 64.000, 66.000, 1.000);
    margin-top: 4px;
}
QTabBar::tab:left:selected {
    border-right: 2px solid rgba(138.000, 180.000, 247.000, 1.000);
}
QTabBar::tab:left:hover {
    border-color: rgba(138.000, 180.000, 247.000, 1.000);
}
QTabBar::tab:left:selected:disabled {
    border-color: rgba(83.000, 87.000, 91.000, 1.000);
}
QTabBar::tab:right {
    border-top-right-radius: 2px;
    border-bottom-right-radius: 2px;
    border-left: 2px solid rgba(63.000, 64.000, 66.000, 1.000);
    margin-top: 4px;
}
QTabBar::tab:right:selected {
    border-left: 2px solid rgba(138.000, 180.000, 247.000, 1.000);
}
QTabBar::tab:right:hover {
    border-color: rgba(138.000, 180.000, 247.000, 1.000);
}
QTabBar::tab:right:selected:disabled {
    border-color: rgba(83.000, 87.000, 91.000, 1.000);
}
QDockWidget {
    border: 1px solid rgba(63.000, 64.000, 66.000, 1.000);
    border-radius: 4px;
}
QDockWidget::title {
    padding: 3px;
    spacing: 4px;
    border: none;
    background-color: rgba(0.000, 0.000, 0.000, 1.000);
}
QDockWidget::close-button:hover,
QDockWidget::float-button:hover {
    background-color: rgba(30.000, 43.000, 60.000, 1.000);
    border-radius: 2px
}

QLCDNumber {
    color: rgba(228.000, 231.000, 235.000, 1.000);
    min-width: 2em;
    margin: 2px;
}
QLabel {
    border: none;
}
QStackedWidget {
    border: none;
}
QToolBox {
    border: none;
}
QToolBox:selected {
    border: 2px solid rgba(138.000, 180.000, 247.000, 1.000);
}
QToolBox::tab {
    background-color: rgba(0.000, 0.000, 0.000, 1.000);
    border-bottom: 2px solid rgba(63.000, 64.000, 66.000, 1.000);
}
QToolBox::tab:selected {
    border-bottom: 2px solid rgba(138.000, 180.000, 247.000, 1.000);
}
QToolBox::tab:selected:disabled {
    border-bottom: 2px solid rgba(83.000, 87.000, 91.000, 1.000);
}
QSplitter {
    border: none;
}
QSplitter::handle {
    margin: 1px 3px;
}
QSplitter::handle:hover {
    background-color: rgba(138.000, 180.000, 247.000, 1.000);
}
QSplitter::handle:horizontal {
    width: 5px;
    image: url(${path}/dark/svg/horizontal_rule__icon-foreground__rotate-90.svg);
}
QSplitter::handle:horizontal:disabled {
    image: url(${path}/dark/svg/horizontal_rule__icon-foreground-disabled__rotate-90.svg);
}
QSplitter::handle:vertical {
    height: 5px;
    image: url(${path}/dark/svg/horizontal_rule__icon-foreground.svg);
}
QSplitter::handle:vertical:disabled {
    image: url(${path}/dark/svg/horizontal_rule__icon-foreground-disabled.svg);
}
QSplitterHandle::item:hover {}
QAbstractScrollArea {
    selection-background-color: rgba(0.000, 72.000, 117.000, 1.000);
    selection-color: rgba(228.000, 231.000, 235.000, 1.000);
    margin: 1px;
}
QAbstractScrollArea:disabled {
    selection-background-color: rgba(228.000, 231.000, 235.000, 1.000);
}
QAbstractScrollArea > .QWidget {
    background-color: transparent;
}
QAbstractScrollArea > .QWidget > .QWidget {
    background-color: transparent;
}
QTextEdit, QPlainTextEdit {
    background-color: rgba(30.000, 29.000, 30.000, 1.000);
}
QTextEdit:focus,
QTextEdit:selected,
QPlainTextEdit:focus,
QPlainTextEdit:selected {
    border: 1px solid rgba(138.000, 180.000, 247.000, 1.000);
    selection-background-color: rgba(18.000, 80.000, 123.000, 1.000);
}
QTextEdit:!focus,
QPlainTextEdit:!focus {
    $env_patch{"version": ">=5.15.0", "value": "selection-background-color: rgba(57.000, 61.000, 65.000, 1.000)"};
}
QTextEdit:!active,
QPlainTextEdit:!active {
    $env_patch{"version": "<5.15.0", "value": "selection-background-color: rgba(57.000, 61.000, 65.000, 1.000)"};
}
QAbstractItemView {
    alternate-background-color: rgba(41.000, 43.000, 46.000, 1.000);
}
QAbstractItemView:item {
    spacing: 6px;
    border-color: transparent;
}
QAbstractItemView:selected:!active,
QAbstractItemView:selected:!focus,
QAbstractItemView::item:selected:!active,
QTreeView::branch:selected:!active {
    background-color: rgba(57.000, 61.000, 65.000, 1.000);
}
QAbstractItemView::item:selected,
QTreeView::branch:selected {
    background-color: rgba(0.000, 72.000, 117.000, 1.000);
    color: rgba(228.000, 231.000, 235.000, 1.000);
}
QAbstractItemView::item:!selected:hover,
QTreeView::branch:!selected:hover {
    background-color: rgba(41.000, 45.000, 46.000, 1.000);
}
QAbstractItemView::item:selected:disabled {
    color: rgba(105.000, 113.000, 119.000, 1.000);
}
QAbstractItemView QLineEdit,
QAbstractItemView QAbstractSpinBox,
QAbstractItemView QComboBox,
QAbstractItemView QAbstractButton {
    padding: 0px;
    margin: 1px;
}
QTreeView::branch {
    border-image: url(${path}/dark/svg/vertical_line__guides-stroke-inactive.svg) 0;
}
QTreeView::branch:active {
    border-image: url(${path}/dark/svg/vertical_line__icon-foreground.svg) 0;
}
QTreeView::branch:disabled {
    border-image: url(${path}/dark/svg/vertical_line__icon-foreground-disabled.svg) 0;
}
QTreeView::branch:has-siblings:adjoins-item,
QTreeView::branch:!has-children:!has-siblings:adjoins-item {
    border-image: none;
}
QTreeView::branch:has-children:!has-siblings:closed,
QTreeView::branch:closed:has-children:has-siblings {
    border-image: none;
    image: url(${path}/dark/svg/chevron_right__icon-foreground.svg);
}
QTreeView::branch:has-children:!has-siblings:closed:disabled,
QTreeView::branch:closed:has-children:has-siblings:disabled {
    image: url(${path}/dark/svg/chevron_right__icon-foreground-disabled.svg);
}
QTreeView::branch:open:has-children:!has-siblings,
QTreeView::branch:open:has-children:has-siblings  {
    border-image: none;
    image: url(${path}/dark/svg/expand_less__icon-foreground__rotate-180.svg);
}
QTreeView::branch:open:has-children:!has-siblings:disabled,
QTreeView::branch:open:has-children:has-siblings:disabled  {
    image: url(${path}/dark/svg/expand_less__icon-foreground-disabled__rotate-180.svg);
}
QTableView {
    gridline-color: rgba(88.000, 89.000, 92.000, 1.000);
    background-color: rgba(0.000, 0.000, 0.000, 1.000);
}
QTableView QTableCornerButton::section {
    border-right: 2px solid transparent;
    border-bottom: 2px solid transparent;
    border-top-left-radius: 2px;
    background-color: rgba(63.000, 64.000, 66.000, 1.000);
}
QTableView QTableCornerButton::section:pressed {
    background-color: rgba(138.000, 180.000, 247.000, 1.000);
}
QTableView QHeaderView{
    background-color: rgba(0.000, 0.000, 0.000, 1.000);
}
QHeaderView {
    padding: 0;
    margin: 0;
    border: none;
    border-radius: 0;
}
QHeaderView::section {
    background-color: rgba(63.000, 64.000, 66.000, 1.000);
    text-align: left;
    padding: 0 4px;
    border: none;
}
QHeaderView::section:horizontal:on,
QHeaderView::section:vertical:on {
    border-color: rgba(138.000, 180.000, 247.000, 1.000);
}
QHeaderView::section:horizontal:on:disabled,
QHeaderView::section:vertical:on:disabled {
    color: rgba(83.000, 87.000, 91.000, 1.000);
    border-color: rgba(83.000, 87.000, 91.000, 1.000);
}
QHeaderView::section:horizontal {
    border-top: 2px solid transparent;
    margin-right: 1px;
}
QHeaderView::section:vertical {
    border-left: 2px solid transparent;
    margin-bottom: 1px;
}
QHeaderView::section::last,
QHeaderView::section::only-one {
    margin: 0;
}
QHeaderView::down-arrow {
    image: url(${path}/dark/svg/expand_less__icon-foreground__rotate-180.svg);
}
QHeaderView::down-arrow:disabled {
    image: url(${path}/dark/svg/expand_less__icon-foreground-disabled__rotate-180.svg);
}
QHeaderView::up-arrow {
    image: url(${path}/dark/svg/expand_less__icon-foreground.svg);
}
QHeaderView::up-arrow:disabled {
    image: url(${path}/dark/svg/expand_less__icon-foreground-disabled.svg);
}
QHeaderView::down-arrow::horizontal,
QHeaderView::up-arrow::horizontal {
    width: 20px;
    padding-right: 2px;
}
QHeaderView::down-arrow::vertical,
QHeaderView::up-arrow::vertical {
    height: 0px;
}
QTreeView[sortingEnabled="false"] QHeaderView::down-arrow,
QTreeView[sortingEnabled="false"] QHeaderView::up-arrow,
QTableView[sortingEnabled="false"] QHeaderView::down-arrow,
QTableView[sortingEnabled="false"] QHeaderView::up-arrow {
    width: 0;
    padding: 0;
}
QCalendarWidget {
    border: 1px solid rgba(63.000, 64.000, 66.000, 1.000);
    border-radius: 4px;
}
QCalendarWidget QWidget {
    background-color: rgba(0.000, 0.000, 0.000, 1.000);
}
QCalendarWidget QTableView {
    alternate-background-color: rgba(63.000, 64.000, 66.000, 1.000);
}
QLineEdit,
QAbstractSpinBox {
    border: 1px solid rgba(63.000, 64.000, 66.000, 1.000);
    padding: 3px 4px;
    min-height: 1em;
    background-color: rgba(63.000, 64.000, 66.000, 1.000);
    border-radius: 4px;
}
QLineEdit:focus,
QAbstractSpinBox:focus {
    border: 1px solid rgba(138.000, 180.000, 247.000, 1.000);
}
QAbstractSpinBox::up-button,
QAbstractSpinBox::down-button {
    subcontrol-origin: border;
    width: 12px;
    height: 4px;
    padding: 3px;
    border-radius: 0;
}
QAbstractSpinBox::up-button:hover,
QAbstractSpinBox::down-button:hover {
    background-color: rgba(88.000, 89.000, 92.000, 1.000);
}
QAbstractSpinBox::up-button {
    subcontrol-position: top right;
    margin: 3px 3px 1px 1px;
}
QAbstractSpinBox::up-arrow {
    height: 23px;
    width: 23px;
    image: url(${path}/dark/svg/arrow_drop_up__icon-foreground.svg);
}
QAbstractSpinBox::up-arrow:disabled {
    image: url(${path}/dark/svg/arrow_drop_up__icon-foreground-disabled.svg);
}
QAbstractSpinBox::down-button {
    subcontrol-position: bottom right;
    margin: 1px 3px 3px 1px;
}
QAbstractSpinBox::down-arrow {
    height: 23px;
    width: 23px;
    image: url(${path}/dark/svg/arrow_drop_up__icon-foreground__rotate-180.svg);
}
QAbstractSpinBox::down-arrow:disabled {
    image: url(${path}/dark/svg/arrow_drop_up__icon-foreground-disabled__rotate-180.svg);
}
QDateTimeEdit::drop-down {
    subcontrol-position: center right;
    border: none;
    padding-right: 4px;
    width: 16px;
    image: url(${path}/dark/svg/calendar_today__icon-foreground.svg);
}
QDateTimeEdit::drop-down:disabled {
    image: url(${path}/dark/svg/calendar_today__icon-foreground-disabled.svg);
}
QDateTimeEdit::down-arrow[calendarPopup="true"] {
    image: none;
}
QDateTimeEdit QAbstractItemView {
    border: 1px solid rgba(138.000, 180.000, 247.000, 1.000);
}
QDateTimeEdit QCalendarWidget QAbstractItemView {
    padding: -1px;
    border: none;
}
QFileDialog > QFrame QAbstractItemView {
    border: none;
}
QFileDialog > QFrame > QFrame QFrame QFrame {
    border: none;
    padding: 0;
}
QFontDialog QListView {
    min-height: 60px;
}
QFontDialog QScrollBar:vertical {
    margin: 0;
}
QComboBox::indicator:checked,
QMenu::indicator:checked {
    width: 18px;
    image: url(${path}/dark/svg/check__icon-foreground.svg);
}
QMenu::indicator {
    width: 18px;
    background-color: rgba(72.000, 73.000, 75.000, 1.000);
    border-radius: 4px;
    margin-left: 3px;
}
QCheckBox {
    spacing: 8px;
}
QGroupBox::title {
    spacing: 6px;
}
QGroupBox::indicator,
QAbstractItemView::indicator {
    height: 18px;
    width: 18px;
}
QCheckBox::indicator:unchecked,
QGroupBox::indicator:unchecked,
QAbstractItemView::indicator:unchecked {
    image: url(${path}/dark/svg/check_box_outline_blank__icon-foreground.svg);
}
QCheckBox::indicator:unchecked:disabled,
QGroupBox::indicator:unchecked:disabled,
QAbstractItemView::indicator:unchecked:disabled {
    image: url(${path}/dark/svg/check_box_outline_blank__icon-foreground-disabled.svg);
}
QCheckBox::indicator:checked,
QGroupBox::indicator:checked,
QAbstractItemView::indicator:checked {
    image: url(${path}/dark/svg/check_box__highlight.svg);
}
QCheckBox::indicator:checked:disabled,
QGroupBox::indicator:checked:disabled,
QAbstractItemView::indicator:checked:disabled {
    image: url(${path}/dark/svg/check_box__icon-foreground-disabled.svg);
}
QCheckBox::indicator:indeterminate,
QAbstractItemView::indicator:indeterminate {
    image: url(${path}/dark/svg/indeterminate_check_box__highlight.svg);
}
QCheckBox::indicator:indeterminate:disabled,
QAbstractItemView::indicator:indeterminate:disabled {
    image: url(${path}/dark/svg/indeterminate_check_box__icon-foreground-disabled.svg);
}
QMenu {
    $env_patch{"version": "<6.0.0", "value": "border-radius: 8px"};
}
QComboBox QAbstractItemView {
    $env_patch{"version": ">=6.0.0", "value": "border-radius: 0; margin: 0"};
}
QStatusBar > QMenu {
    $env_patch{"version": ">=6.0.0", "value": "border-radius: 0; margin: 0"};
}
PlotWidget {
    padding: 0px;
}

"""
