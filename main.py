import datetime
import hashlib
import os
import sys

from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QDropEvent
from PyQt5.QtWidgets import QAbstractItemView, QApplication, QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, \
    QHeaderView, QListWidget, QPushButton, QFileDialog, QMessageBox, QDesktopWidget, QAction, QMenu, QHBoxLayout, \
    QDialog, QLabel, QLineEdit, QDialogButtonBox, QCheckBox
from mutagen.flac import FLAC


class TableWidgetDragRows(QTableWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # set up on demand sorting
        header = self.horizontalHeader()
        header.setSortIndicatorShown(True)
        header.sortIndicatorChanged.connect(self.sortItems)

        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDragDropOverwriteMode(False)
        self.setDropIndicatorShown(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setDragDropMode(QAbstractItemView.InternalMove)

    def dropEvent(self, event: QDropEvent):
        if not event.isAccepted() and event.source() == self:
            drop_row = self.drop_on(event)

            rows = sorted(set(item.row() for item in self.selectedItems()))
            rows_to_move = [
                [QTableWidgetItem(self.item(row_index, column_index)) for column_index in range(self.columnCount())]
                for row_index in rows]
            for row_index in reversed(rows):
                self.removeRow(row_index)
                if row_index < drop_row:
                    drop_row -= 1

            for row_index, data in enumerate(rows_to_move):
                row_index += drop_row
                self.insertRow(row_index)
                for column_index, column_data in enumerate(data):
                    self.setItem(row_index, column_index, column_data)
            event.accept()

            for row_index in range(len(rows_to_move)):  # maybe can be done smarter
                for col in range(self.columnCount()):
                    self.item(drop_row + row_index, col).setSelected(True)

        super().dropEvent(event)

    def drop_on(self, event):
        index = self.indexAt(event.pos())
        if not index.isValid():
            return self.rowCount()
        return index.row() + 1 if self.is_below(event.pos(), index) else index.row()

    def is_below(self, pos, index):
        rect = self.visualRect(index)
        margin = 2
        if pos.y() - rect.top() < margin:
            return False
        elif rect.bottom() - pos.y() < margin:
            return True
        # noinspection PyTypeChecker
        return rect.contains(pos, True) and not (
                int(self.model().flags(index)) & Qt.ItemIsDropEnabled) and pos.y() >= rect.center().y()


class FLACTagEditor(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()

    def center(self):
        qr = self.frameGeometry()
        cp = QDesktopWidget().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def initUI(self):
        self.setWindowTitle('FLAC Tag Editor')
        self.setGeometry(100, 100, 800, 600)  # 表示窗口左上角的 x 坐标、y 坐标，以及窗口的宽度和高度
        self.center()

        self.import_button = QPushButton('Import FLAC File', self)
        self.import_button.clicked.connect(self.importFLAC)

        self.info_button = QPushButton('Show FLAC Info', self)
        self.info_button.clicked.connect(self.showFLACInfo)

        self.delete_selected_button = QPushButton('Delete Selected', self)
        self.delete_selected_button.clicked.connect(self.deleteSelectedFiles)
        self.delete_selected_button.setEnabled(False)  # 初始状态禁用

        self.clear_button = QPushButton('Clear', self)
        self.clear_button.clicked.connect(self.clearList)


        button_layout = QHBoxLayout()
        button_layout.addWidget(self.import_button)
        button_layout.addWidget(self.info_button)
        button_layout.addWidget(self.delete_selected_button)
        button_layout.addWidget(self.clear_button)

        self.list_widget = DropList(self)
        self.list_widget.setAcceptDrops(True)
        self.list_widget.setFixedHeight(150)

        self.table = TableWidgetDragRows(self)
        self.table.setColumnCount(2)
        self.table.verticalHeader().setVisible(False)
        self.table.setHorizontalHeaderLabels(['Field Name', 'Value'])
        self.table.setColumnWidth(0, 300)
        self.table.setColumnWidth(1, 450)

        # 创建添加、删除和保存按钮
        self.add_button = QPushButton('Add', self)
        self.add_button.clicked.connect(self.addTableRow)

        self.delete_button = QPushButton('Delete', self)
        self.delete_button.clicked.connect(self.deleteTableRow)

        self.save_button = QPushButton('Save', self)
        self.save_button.clicked.connect(self.saveFLAC)

        # 创建复选框和单行文本框
        self.use_padding_checkbox = QCheckBox('Use New Padding', self)
        self.padding_lineedit = QLineEdit(self)
        self.padding_lineedit.setPlaceholderText("Enter padding value")
        self.padding_lineedit.setEnabled(False)  # 初始状态禁用

        # 为复选框的状态切换设置事件处理函数
        self.use_padding_checkbox.stateChanged.connect(self.updatePaddingLineEditState)

        # 创建布局并添加控件
        layout = QVBoxLayout()
        layout.addLayout(button_layout)
        layout.addWidget(self.list_widget)
        layout.addWidget(self.table)

        # 创建水平布局来放置添加和删除按钮
        buttons_layout_left = QHBoxLayout()
        buttons_layout_left.addWidget(self.add_button)
        buttons_layout_left.addWidget(self.delete_button)

        # 创建水平布局来放置复选框和文本框以及保存按钮
        buttons_layout_right = QHBoxLayout()
        buttons_layout_right.addWidget(self.use_padding_checkbox)
        buttons_layout_right.addWidget(self.padding_lineedit)
        buttons_layout_right.addWidget(self.save_button)

        # 创建水平布局用于将左侧按钮和右侧控件放在一起
        buttons_layout = QHBoxLayout()
        buttons_layout.addLayout(buttons_layout_left)
        buttons_layout.addStretch(1)  # 添加弹簧，使右侧控件靠右对齐
        buttons_layout.addLayout(buttons_layout_right)

        # 将按钮布局添加到主垂直布局中
        layout.addLayout(buttons_layout)

        self.setLayout(layout)


        self.list_widget.itemSelectionChanged.connect(self.showSelectedFLACInfo)

    def showFLACInfo(self):
        selected_items = self.list_widget.selectedItems()
        if selected_items:
            filepath = selected_items[0].text()

            # Call the code to get FLAC information
            file_hash, md5, sample_rate, bits_per_sample, length, padding_length, vendor_string = self.getFLACInfo(
                filepath)

            # Construct the message to display
            msg_text = f'File Hash: {file_hash}\nAudio MD5: {md5}\nSample Rate: {sample_rate} kHz\nBits Per Sample: {bits_per_sample}\nLength: {length}\n'
            msg_text += f'Padding Length: {padding_length}\nVendor String: {vendor_string}\n'

            # Display the message in a QMessageBox
            msg = QMessageBox()
            msg.setWindowTitle("FLAC Information")
            msg.setText(msg_text)
            msg.exec_()
        else:
            QMessageBox.warning(self, "Warning", "Please select a FLAC file first.")

    def getFLACInfo(self, filepath):
        # Initialize variables to store FLAC information
        file_hash = ''
        md5 = ''
        sample_rate = ''
        bits_per_sample = ''
        length = ''

        padding_length = ''
        vendor_string = ''

        try:
            # Calculate file hash
            file_hash = get_hash(filepath)

            # Read FLAC file
            flac = FLAC(filepath)
            info = flac.info

            # Get FLAC file information
            md5 = hex(info.md5_signature).split('x')[-1]
            sample_rate = info.sample_rate / 1000
            bits_per_sample = info.bits_per_sample
            length = format_seconds(info.length)

            # Get padding length
            for block in flac.metadata_blocks:
                if block.code == 1:
                    padding_length = block.length

            # Get vendor string
            try:
                vendor_string = flac.tags.vendor
            except:
                vendor_string = '获取失败'

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to read FLAC information: {str(e)}")

        # Return FLAC information
        return file_hash, md5, sample_rate, bits_per_sample, length, padding_length, vendor_string

    def updatePaddingLineEditState(self, state):
        # 根据复选框状态设置单行文本框的启用状态
        if state == Qt.Checked:
            self.padding_lineedit.setEnabled(True)
        else:
            self.padding_lineedit.setEnabled(False)

    def deleteSelectedFiles(self):
        selected_items = self.list_widget.selectedItems()
        if selected_items:
            for item in selected_items:
                self.list_widget.takeItem(self.list_widget.row(item))
        self.updateDeleteSelectedButtonState()

    def updateDeleteSelectedButtonState(self):
        selected_items = self.list_widget.selectedItems()
        self.delete_selected_button.setEnabled(bool(selected_items))

    def clearList(self):
        self.list_widget.clear()  # 清空列表
        self.updateDeleteSelectedButtonState()  # 更新删除按钮状态


    def showSelectedFLACInfo(self):
        selected_items = self.list_widget.selectedItems()
        if selected_items:
            filepath = selected_items[0].text()
            # self.metadata = FLAC(filepath).tags
            # self.populateTable()
            try:
                self.metadata = FLAC(filepath).tags
                self.populateTable()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to read tags from {filepath}: {str(e)}")
                self.table.setRowCount(0)
        else:
            self.table.setRowCount(0)

        self.updateDeleteSelectedButtonState()  # 更新删除按钮的状态

    def populateTable(self):
        self.table.setRowCount(len(self.metadata))

        row = 0
        for key, value in self.metadata:
            field_item = QTableWidgetItem(key)
            value_item = QTableWidgetItem(str(value))  # Convert to string if it's a list
            self.table.setItem(row, 0, field_item)
            self.table.setItem(row, 1, value_item)
            row += 1

        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)

    def importFLAC(self):
        filepaths, _ = QFileDialog.getOpenFileNames(self, 'Import FLAC Files', '', 'FLAC Files (*.flac)')
        if filepaths:
            for filepath in filepaths:
                if self.isFLAC(filepath):
                    self.list_widget.addItem(filepath)
                else:
                    print(f"{filepath} is not a FLAC file. Skipping.")
            # for filepath in filepaths:
            #     self.list_widget.addItem(filepath)

    def saveFLAC(self):
        # Here you should implement a function to save the edited metadata
        print("save")
        metadata_dict = {}
        for row in range(self.table.rowCount()):
            field_name_item = self.table.item(row, 0)
            value_item = self.table.item(row, 1)
            if field_name_item and value_item:
                field_name = field_name_item.text()
                value = value_item.text()
                metadata_dict[field_name] = value

        # 使用QMessageBox显示字典内容
        msg = QMessageBox()
        msg.setWindowTitle("Metadata Dictionary")

        # 检查复选框状态，根据需要显示单行文本框的内容
        use_padding = self.use_padding_checkbox.isChecked()

        # 如果复选框被勾选但是单行文本框为空或者不是数字，报错
        if use_padding:
            padding_value = self.padding_lineedit.text()
            if not padding_value or not padding_value.isdigit():
                QMessageBox.critical(self, "Error",
                                     "Padding value must be a non-empty number when 'Use New Padding' is checked.")
                return

        padding_value = self.padding_lineedit.text() if use_padding else "Not used"

        # 提示框中显示是否勾选了新padding选项以及相应的数值
        msg = QMessageBox()
        msg.setWindowTitle("Metadata Dictionary")
        msg_text = f"Use New Padding: {use_padding}\nPadding Value: {padding_value}\n\n{metadata_dict}"
        msg.setText(msg_text)
        msg.exec_()
        # msg.setText(str(metadata_dict))
        # msg.exec_()

    def isFLAC(self, filepath):
        _, ext = os.path.splitext(filepath)
        return ext.lower() == ".flac"

    # def addTableRow(self):
    #     dialog = AddRowDialog(self)
    #     if dialog.exec_():
    #         field_name = dialog.field_name.text()
    #         value = dialog.value.text()
    #
    #         row_count = self.table.rowCount()
    #         self.table.insertRow(row_count)
    #         self.table.setItem(row_count, 0, QTableWidgetItem(field_name))
    #         self.table.setItem(row_count, 1, QTableWidgetItem(value))

    def addTableRow(self):
        row_count = self.table.rowCount()
        self.table.insertRow(row_count)
        self.table.setItem(row_count, 0, QTableWidgetItem(""))
        self.table.setItem(row_count, 1, QTableWidgetItem(""))
        self.table.setCurrentCell(row_count, 0)  # 设置焦点到新行的"Field Name"列

        item = self.table.item(row_count, 0)
        if item:
            self.table.editItem(item)  # 进入编辑状态
            self.table.scrollToItem(item, QtWidgets.QAbstractItemView.PositionAtTop)  # 滚动到可见区域

    def deleteTableRow(self):
        selected_rows = self.table.selectionModel().selectedRows()
        for row in reversed(selected_rows):
            self.table.removeRow(row.row())


class AddRowDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Add Row")
        self.initUI()

    def initUI(self):
        self.field_name_label = QLabel("Field Name:")
        self.field_name = QLineEdit()
        self.value_label = QLabel("Value:")
        self.value = QLineEdit()

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addWidget(self.field_name_label)
        layout.addWidget(self.field_name)
        layout.addWidget(self.value_label)
        layout.addWidget(self.value)
        layout.addWidget(button_box)

        self.setLayout(layout)


class DropList(QListWidget):
    def __init__(self, parent=None):
        super(DropList, self).__init__(parent)
        self.setAcceptDrops(True)

        self.initContextMenu()  # 右键菜单

    def initContextMenu(self):
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.showContextMenu)

        self.delete_action = QAction("Delete", self)
        self.delete_action.triggered.connect(self.deleteSelectedItem)

    def showContextMenu(self, pos):
        menu = QMenu(self)
        menu.addAction(self.delete_action)
        menu.exec_(self.mapToGlobal(pos))

    def deleteSelectedItem(self):
        for item in self.selectedItems():
            self.takeItem(self.row(item))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        md = event.mimeData()
        if md.hasUrls():
            for url in md.urls():
                # self.addItem(url.toLocalFile())
                filepath = url.toLocalFile()
                if self.parent().isFLAC(filepath):
                    self.addItem(filepath)
                else:
                    print(f"{filepath} is not a FLAC file. Skipping.")
            event.acceptProposedAction()


def get_hash(filename):
    with open(filename, 'rb') as f:
        file_hash = hashlib.md5()
        while chunk := f.read(8192):
            file_hash.update(chunk)
        return file_hash.hexdigest()


def format_seconds(seconds):
    td = datetime.timedelta(seconds=seconds)
    hours, remainder = divmod(td.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    time_str = f'{hours:02}:{minutes:02}:{seconds:02}'
    return time_str


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = FLACTagEditor()
    window.show()
    sys.exit(app.exec_())
