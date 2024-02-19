import datetime
import hashlib
import os
import sys

from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt, QEvent
from PyQt5.QtGui import QDropEvent, QBrush, QColor, QPixmap, QImage
from PyQt5.QtWidgets import QAbstractItemView, QApplication, QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, \
    QHeaderView, QListWidget, QPushButton, QFileDialog, QMessageBox, QDesktopWidget, QHBoxLayout, \
    QLineEdit, QCheckBox, QDialog, QLabel, QMenu, QAction, QGridLayout
from mutagen import File
from mutagen.flac import FLAC, Picture


class TableWidgetDragRows(QTableWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Enable sorting indicators in the header.
        header = self.horizontalHeader()
        header.setSortIndicatorShown(True)
        header.sortIndicatorChanged.connect(self.sortItems)

        # Enable drag and drop functionality.
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDragDropOverwriteMode(False)
        self.setDropIndicatorShown(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setDragDropMode(QAbstractItemView.InternalMove)

    def dropEvent(self, event: QDropEvent):
        """Handle drop event."""

        # If the event is not already handled and source is self.
        if not event.isAccepted() and event.source() == self:

            # Get the drop row.
            drop_row = self.drop_on(event)

            # Get the rows to move.
            rows = sorted(set(item.row() for item in self.selectedItems()))
            rows_to_move = [
                [QTableWidgetItem(self.item(row_index, column_index)) for column_index in range(self.columnCount())]
                for row_index in rows]

            # Remove selected rows.
            for row_index in reversed(rows):
                self.removeRow(row_index)
                if row_index < drop_row:
                    drop_row -= 1

            # Insert rows at the drop position.
            for row_index, data in enumerate(rows_to_move):
                row_index += drop_row
                self.insertRow(row_index)
                for column_index, column_data in enumerate(data):
                    self.setItem(row_index, column_index, column_data)

            # Accept the event.
            event.accept()

            # Select the moved rows.
            for row_index in range(len(rows_to_move)):
                for col in range(self.columnCount()):
                    self.item(drop_row + row_index, col).setSelected(True)

        # Call the parent class dropEvent method.
        super().dropEvent(event)

    def drop_on(self, event):
        """Determine where the drop occurred."""

        # Get the index at drop position.
        index = self.indexAt(event.pos())

        # Return the row count if the index is not valid.
        if not index.isValid():
            return self.rowCount()

        # Return the row below the drop position if it is below the index; otherwise, return the index's row.
        return index.row() + 1 if self.is_below(event.pos(), index) else index.row()

    def is_below(self, pos, index):
        """Check if the drop position is below the index."""

        # Get visual rect of index.
        rect = self.visualRect(index)
        margin = 2

        # If the drop position is above the index, return False.
        if pos.y() - rect.top() < margin:
            return False

        # If the drop position is below the index, return True.
        elif rect.bottom() - pos.y() < margin:
            return True

        # Check if position is within the item's rectangle and not on a drop-enabled item.
        return rect.contains(pos, True) and not (
                int(self.model().flags(index)) & Qt.ItemIsDropEnabled) and pos.y() >= rect.center().y()


class DropList(QListWidget):
    def __init__(self, parent=None):
        super(DropList, self).__init__(parent)

        # Enable accepting drops.
        self.setAcceptDrops(True)

        # 支持多选
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)

    def dragEnterEvent(self, event):
        """Handle drag enter event."""
        # Check if the event contains URLs.
        if event.mimeData().hasUrls():
            # Accept the proposed action.
            event.acceptProposedAction()
        else:
            # Ignore the event if it doesn't contain URLs.
            event.ignore()

    def dragMoveEvent(self, event):
        """Handle drag move event."""
        # Check if the event contains URLs.
        if event.mimeData().hasUrls():
            # Accept the proposed action.
            event.acceptProposedAction()
        else:
            # Ignore the event if it doesn't contain URLs.
            event.ignore()

    def dropEvent(self, event):
        """Handle drop event."""
        # Get the mime data from the event.
        md = event.mimeData()
        # Check if the mime data contains URLs.
        if md.hasUrls():
            # Iterate through the URLs.
            for url in md.urls():
                # Get the local file path from the URL.
                filepath = url.toLocalFile()
                # Check if the file path corresponds to a FLAC file.
                if self.parent().isFLAC(filepath):
                    # Add the file path to the list.
                    self.addItem(filepath)
                else:
                    print(f"{filepath} is not a FLAC file. Skipping.")
            self.sortItems()
            # Accept the proposed action.
            event.acceptProposedAction()


class FLACTagEditor(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()

        # 如果以命令行执行并附带文件路径参数，则将文件添加到列表中
        if len(sys.argv) > 1:
            file_paths = sys.argv[1:]
            for file_path in file_paths:
                if self.isFLAC(file_path):
                    self.list_widget.addItem(file_path)
                else:
                    print(f"{file_path} is not a FLAC file. Skipping.")

    def initUI(self):

        # Set the window title.
        self.setWindowTitle('FLAC Tag Editor')

        # Set the window's geometry (x, y, width, height).
        self.setGeometry(100, 100, 800, 600)

        # Center the window.
        self.center()

        # Create a button for importing FLAC files.
        self.import_button = QPushButton('Import FLAC File', self)
        self.import_button.clicked.connect(self.importFLAC)

        self.blocks_button = QPushButton("Show Blocks")
        self.blocks_button.clicked.connect(self.show_blocks_window)

        # Create a button for deleting selected files.
        self.delete_button = QPushButton('Delete', self)
        self.delete_button.clicked.connect(self.deleteSelectedFiles)

        # Create a button for clearing the list.
        self.clear_button = QPushButton('Clear', self)
        self.clear_button.clicked.connect(self.clearList)

        # Create a horizontal layout for buttons.
        top_buttons_layout = QHBoxLayout()
        top_buttons_layout.addWidget(self.import_button)
        top_buttons_layout.addWidget(self.blocks_button)
        top_buttons_layout.addWidget(self.delete_button)
        top_buttons_layout.addWidget(self.clear_button)

        # Create a drop list widget.
        self.list_widget = DropList(self)
        # Enable accepting drops.
        self.list_widget.setAcceptDrops(True)
        # Set the fixed height of the list widget.
        self.list_widget.setFixedHeight(150)

        # Create a table widget for drag and drop rows.
        self.table = TableWidgetDragRows(self)
        # Set the number of columns in the table.
        self.table.setColumnCount(2)
        # Hide the vertical header.
        self.table.verticalHeader().setVisible(False)
        # Set the horizontal header labels.
        self.table.setHorizontalHeaderLabels(['Field Name', 'Value'])
        # Set the width of the first column.
        self.table.setColumnWidth(0, 300)
        # Set the width of the second column.
        self.table.setColumnWidth(1, 400)

        # Create a button for adding rows.
        self.add_button = QPushButton('Add', self)
        self.add_button.clicked.connect(self.addTableRow)

        # Create a button for deleting rows.
        self.delete_button = QPushButton('Delete', self)
        self.delete_button.clicked.connect(self.deleteTableRow)

        # Create a button for saving changes.
        self.save_button = QPushButton('Save', self)
        self.save_button.clicked.connect(self.saveFLAC)

        # Create a checkbox for padding.
        self.use_padding_checkbox = QCheckBox('Use New Padding', self)
        # Create a line edit for entering padding value.
        self.padding_lineedit = QLineEdit(self)
        # Set placeholder text for the line edit.
        self.padding_lineedit.setPlaceholderText("Enter padding value")
        # Initially disable the line edit.
        self.padding_lineedit.setEnabled(False)

        self.use_padding_checkbox.stateChanged.connect(self.updatePaddingLineEditState)

        # Create a horizontal layout for add and delete buttons.
        buttons_layout_left = QHBoxLayout()
        buttons_layout_left.addWidget(self.add_button)
        buttons_layout_left.addWidget(self.delete_button)

        # Create a horizontal layout for checkbox, line edit, and save button.
        buttons_layout_right = QHBoxLayout()
        buttons_layout_right.addWidget(self.use_padding_checkbox)
        buttons_layout_right.addWidget(self.padding_lineedit)
        buttons_layout_right.addWidget(self.save_button)

        # Create a horizontal layout to combine left and right button layouts.
        bottom_buttons_layout = QHBoxLayout()
        bottom_buttons_layout.addLayout(buttons_layout_left)
        bottom_buttons_layout.addStretch(1)  # Add stretch to align right-side widgets to the right.
        bottom_buttons_layout.addLayout(buttons_layout_right)

        # Create the main layout.
        layout = QVBoxLayout()
        layout.addLayout(top_buttons_layout)
        layout.addWidget(self.list_widget)
        layout.addWidget(self.table)
        layout.addLayout(bottom_buttons_layout)

        # Set the main layout
        self.setLayout(layout)

        self.list_widget.itemSelectionChanged.connect(self.showTags)

    def center(self):
        """Center the window on the screen."""
        qr = self.frameGeometry()
        cp = QDesktopWidget().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def show_blocks_window(self):
        selected_items = self.list_widget.selectedItems()
        if selected_items:
            filepath = selected_items[0].text()
            cover_window = BlocksWindow(filepath)
            cover_window.exec_()
        else:
            QMessageBox.warning(self, "Warning", "Please select a FLAC file first.")

    def importFLAC(self):
        """Import FLAC files."""
        filepaths, _ = QFileDialog.getOpenFileNames(self, 'Import FLAC Files', '', 'FLAC Files (*.flac)')
        if filepaths:
            for filepath in filepaths:
                if self.isFLAC(filepath):
                    self.list_widget.addItem(filepath)
                else:
                    print(f"{filepath} is not a FLAC file. Skipping.")
        self.list_widget.sortItems()

    def deleteSelectedFiles(self):
        """Delete selected files from the list."""
        selected_items = self.list_widget.selectedItems()
        if selected_items:
            for item in selected_items:
                self.list_widget.takeItem(self.list_widget.row(item))
        else:
            QMessageBox.warning(self, "Warning", "Please select a FLAC file first.")

    def clearList(self):
        """Clear all items from the list."""
        # Clear the list
        self.list_widget.clear()

    def showTags(self):
        """Show tags of the selected FLAC file."""
        selected_items = self.list_widget.selectedItems()
        if selected_items:

            # 如果选中单个文件
            if len(selected_items) == 1:
                filepath = selected_items[0].text()
                try:
                    self.metadata = FLAC(filepath).tags
                    self.populateTable()
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to read tags from {filepath}: {str(e)}")
                    self.table.setRowCount(0)
            # 如果选中多个文件
            else:
                # 用于存储各个文件的标签字段及其顺序的列表
                tag_fields = []

                # 遍历选中的文件，获取每个文件的标签字段及其顺序
                for item in selected_items:
                    filepath = item.text()
                    flac = FLAC(filepath)
                    tag_fields.append([key for key, _ in flac.tags])

                # 检查标签字段列表是否完全相同（包括顺序）
                is_same_tags = all(tag_fields[0] == tag_list for tag_list in tag_fields)

                if not is_same_tags:
                    self.table.setRowCount(0)
                    QMessageBox.critical(self, "Error", "Selected files have different tag fields or orders.")
                    # self.list_widget.clearSelection()
                    return

                # 清空表格并设置行数
                self.table.setRowCount(len(tag_fields[0]))

                # 填充表格
                for row, tag in enumerate(tag_fields[0]):
                    # 设置标签名称
                    field_item = QTableWidgetItem(tag)
                    self.table.setItem(row, 0, field_item)

                    # 获取所有文件中相同标签的值
                    values = set()
                    for item in selected_items:
                        filepath = item.text()
                        flac = FLAC(filepath)
                        file_value = flac.tags.get(tag, [''])[0]
                        values.add(file_value)

                    if len(values) == 1:
                        value_item = QTableWidgetItem(next(iter(values)))
                    else:
                        sorted_values = sorted(values)  # 对值进行排序
                        text = "; ".join(sorted_values)

                        value_item = QTableWidgetItem(f"<Multivalued> {text}")
                        self.table.setItem(row, 1, value_item)

                        value_item.setForeground(QBrush(QColor(128, 128, 128)))  # 设置文本颜色为灰色

                    self.table.setItem(row, 1, value_item)


        else:
            self.table.setRowCount(0)

    def populateTable(self):
        """Populate the table with FLAC metadata."""

        # Set the number of rows in the table
        self.table.setRowCount(len(self.metadata))

        # Initialize the row index
        row = 0

        # Iterate through metadata items
        for key, value in self.metadata:
            # Create a QTableWidgetItem for the field key
            field_item = QTableWidgetItem(key)
            # Create a QTableWidgetItem for the field value
            value_item = QTableWidgetItem(value)
            # Set the field item in the first column
            self.table.setItem(row, 0, field_item)
            # Set the value item in the second column
            self.table.setItem(row, 1, value_item)
            # Increment the row index
            row += 1

        # Resize table columns interactively
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)

    def addTableRow(self):
        """Add a new row to the table."""

        # Get the current row count
        row_count = self.table.rowCount()

        # Insert a new row
        self.table.insertRow(row_count)

        # Set an empty item in the "Field Name" column
        self.table.setItem(row_count, 0, QTableWidgetItem(""))

        # Set an empty item in the "Value" column
        self.table.setItem(row_count, 1, QTableWidgetItem(""))

        # Set focus to the "Field Name" column of the new row
        self.table.setCurrentCell(row_count, 0)

        # Get the item in the "Field Name" column
        item = self.table.item(row_count, 0)
        if item:
            # Enter edit mode for the item
            self.table.editItem(item)

            # Scroll to make the item visible
            self.table.scrollToItem(item, QtWidgets.QAbstractItemView.PositionAtTop)  # 滚动到可见区域

    def deleteTableRow(self):
        """Delete selected rows from the table."""

        # Get selected rows
        selected_rows = self.table.selectionModel().selectedRows()
        # Iterate over selected rows in reverse order
        for row in reversed(selected_rows):
            # Remove the row from the table
            self.table.removeRow(row.row())

    def updatePaddingLineEditState(self, state):
        """Update the state of the padding line edit based on the checkbox state.

        Args:
            state: The state of the checkbox.
        """

        # Enable/disable the padding line edit based on the checkbox state
        if state == Qt.Checked:
            self.padding_lineedit.setEnabled(True)
        else:
            self.padding_lineedit.setEnabled(False)

    def saveFLAC(self):
        """Save metadata to a FLAC file."""

        # Dictionary to store original tag values
        original_tag_values = {}

        # Dictionary to store metadata
        metadata_dict = {}

        # Iterate over rows in the table
        for row in range(self.table.rowCount()):
            # Get the item in the "Field Name" column
            field_name_item = self.table.item(row, 0)
            # Get the item in the "Value" column
            value_item = self.table.item(row, 1)
            # If both items exist
            if field_name_item and value_item:
                # Get the text of the "Field Name" item
                field_name = field_name_item.text()
                # Get the text of the "Value" item
                value = value_item.text()
                # Add the field name and value to the metadata dictionary
                metadata_dict[field_name] = value

        # Check if padding is enabled
        use_padding = self.use_padding_checkbox.isChecked()

        # Check if padding is enabled and the padding value is valid
        if use_padding:
            padding_value = self.padding_lineedit.text()
            if not padding_value or not padding_value.isdigit():
                QMessageBox.critical(self, "Error",
                                     "Padding value must be a non-empty number when 'Use New Padding' is checked.")
                return

        # Get selected items from the list widget
        selected_items = self.list_widget.selectedItems()
        if selected_items:

            try:
                for item in selected_items:
                    filepath = item.text()
                    flac = File(filepath)
                    original_tag_values[filepath] = {tag: flac[tag] for tag in metadata_dict if flac.get(tag)}
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to read tags from {filepath}: {str(e)}")
                return

            try:
                # Iterate over selected files
                for item in selected_items:
                    filepath = item.text()
                    flac = File(filepath)

                    # Clear existing tags
                    if flac.tags:
                        flac.tags.clear()

                    # Set metadata tags
                    for k, v in metadata_dict.items():
                        if v.startswith("<Multivalued> "):
                            # Restore original value
                            if filepath in original_tag_values and k in original_tag_values[filepath]:
                                flac[k] = original_tag_values[filepath][k]
                        else:
                            flac[k] = v

                    if use_padding:
                        # Save FLAC file with new padding
                        flac.save(padding=self.new_padding)
                    else:
                        # Save FLAC file without new padding
                        flac.save()

                # Display success message
                QMessageBox.information(self, "Success", "Tags saved successfully.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save tags to {filepath}: {str(e)}")
                self.table.setRowCount(0)  # Clear the table
                return
        else:
            QMessageBox.warning(self, "Warning", "Please select a FLAC file first.")
            return

    def new_padding(self, padding):
        """Get the new padding value from the padding line edit."""
        # Return the integer value of the text in the padding line edit
        return int(self.padding_lineedit.text())

    def isFLAC(self, filepath):
        """Check if the file at the given filepath is a FLAC file."""
        # Split the filepath to get the extension
        _, ext = os.path.splitext(filepath)
        # Check if the extension is ".flac" (case-insensitive)
        return ext.lower() == ".flac"


def get_hash(filename):
    """Calculate the MD5 hash of a file.

    Args:
        filename (str): The path to the file.

    Returns:
        str: The MD5 hash of the file.
    """
    with open(filename, 'rb') as f:
        file_hash = hashlib.md5()
        while chunk := f.read(8192):
            file_hash.update(chunk)
        return file_hash.hexdigest()


def format_seconds(seconds):
    """Format seconds into a human-readable time string.

    Args:
        seconds (int): The number of seconds.

    Returns:
        str: A formatted time string (HH:MM:SS).
    """
    td = datetime.timedelta(seconds=seconds)
    hours, remainder = divmod(td.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    time_str = f'{hours:02}:{minutes:02}:{seconds:02}'
    return time_str


def bits_per_second_to_kbps(bits_per_second):
    """Convert bits per second to kilobits per second (kbps).

    Args:
        bits_per_second (int): Bits per second.

    Returns:
        str: The converted value in kilobits per second.
    """
    kbps = round(bits_per_second / 1000)
    return kbps


class CoverWindow(QDialog):
    # TODO: 批量修改
    def __init__(self, flac_path):
        super().__init__()

        self.resize(400, 400)  # 设置窗口的初始大小

        self.flac_path = flac_path
        self.setWindowTitle("Set Cover")
        self.cover_label = QLabel()
        self.cover_label.setAlignment(Qt.AlignCenter)
        self.file_size_label = QLabel()
        self.resolution_label = QLabel()
        self.height_label = QLabel("Height:")
        self.width_label = QLabel("Width:")
        self.depth_label = QLabel("Depth:")
        self.desc_label = QLabel("Description:")
        self.height_edit = QLineEdit()
        self.width_edit = QLineEdit()
        self.depth_edit = QLineEdit()
        self.desc_edit = QLineEdit()
        self.save_button = QPushButton("Save")
        self.cancel_button = QPushButton("Cancel")

        # 创建按钮布局
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)

        layout = QVBoxLayout()
        layout.addWidget(self.cover_label)
        layout.addWidget(self.file_size_label)
        layout.addWidget(self.resolution_label)
        layout.addWidget(self.width_label)
        layout.addWidget(self.width_edit)
        layout.addWidget(self.height_label)
        layout.addWidget(self.height_edit)
        layout.addWidget(self.depth_label)
        layout.addWidget(self.depth_edit)
        layout.addWidget(self.desc_label)
        layout.addWidget(self.desc_edit)
        layout.addLayout(button_layout)
        self.setLayout(layout)

        self.showCoverImage(self.flac_path)
        self.save_button.clicked.connect(self.saveTags)
        self.cancel_button.clicked.connect(self.close)

        # self.cover_label.mouseDoubleClickEvent = self.chooseImage
        # 创建右键菜单
        self.context_menu = QMenu(self)
        self.import_action = QAction("Import", self)
        self.export_action = QAction("Export", self)

        # 将动作添加到右键菜单
        self.context_menu.addAction(self.import_action)
        self.context_menu.addAction(self.export_action)
        self.import_action.triggered.connect(self.chooseImage)
        self.export_action.triggered.connect(self.exportCover)

        # 在图片组件上安装事件过滤器
        self.cover_label.installEventFilter(self)

    def eventFilter(self, source, event):
        """事件过滤器函数，捕获图片组件的右键点击事件，并显示右键菜单。"""
        if source is self.cover_label and event.type() == QEvent.ContextMenu:
            # 显示右键菜单
            self.context_menu.exec_(event.globalPos())
            return True
        return super().eventFilter(source, event)

    def exportCover(self):
        """导出封面图片到文件."""
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Cover Image", "cover.jpg", "JPEG Files (*.jpg)")
        if file_path:
            # 将图片数据保存到文件
            with open(file_path, 'wb') as f:
                f.write(self.picdata)
        QMessageBox.information(self, "Success", "Cover saved successfully.")

    def showCoverImage(self, flac_path):
        if not flac_path:
            return
        try:
            audio = FLAC(flac_path)
            pictures = audio.pictures
            for p in pictures:
                print(vars(p).keys())
                if p.type == 3:
                    self.picdata = p.data
                    img = QImage()
                    img.loadFromData(p.data)
                    img_scaled = img.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    # 打开设置好的图片
                    pixmap = QPixmap(img_scaled)
                    self.cover_label.setPixmap(pixmap)

                    pic_len = len(self.picdata)
                    self.file_size_label.setText(f"File Size: {format_size(pic_len)} ({pic_len})")
                    self.resolution_label.setText(f"Resolution: {img.size().width()}x{img.size().height()}")

                    self.width_edit.setText(str(p.width))
                    self.height_edit.setText(str(p.height))
                    self.depth_edit.setText(str(p.depth))
                    self.desc_edit.setText(str(p.desc))

                    return  # Exit after displaying the first cover
            # If no cover found, clear cover label
            self.cover_label.clear()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error displaying cover image: {e}")
            return

    def saveTags(self):
        if not self.flac_path:
            return
        if not self.picdata:
            return
        audio = FLAC(self.flac_path)
        pictures = audio.pictures
        print(pictures)
        picture = Picture()
        picture.type = 3
        picture.mime = 'image/jpeg'
        picture.data = self.picdata

        try:
            height_text = self.height_edit.text()
            width_text = self.width_edit.text()
            depth_text = self.depth_edit.text()

            # 如果文本框中的文本为空，则将相应的值设置为None
            height = int(height_text) if height_text else None
            width = int(width_text) if width_text else None
            depth = int(depth_text) if depth_text else None

            picture.width = width
            picture.height = height
            picture.depth = depth
        except ValueError:
            QMessageBox.critical(self, "Error", "Invalid input. Please enter valid numbers for height, width, "
                                                "and depth.")
            return

        picture.desc = self.desc_edit.text()
        audio.clear_pictures()
        audio.add_picture(picture)
        audio.save()
        QMessageBox.information(self, "Success", "Tags saved successfully.")

    def chooseImage(self):  # event:
        """Handle double-click event on the cover image."""
        # if event.button() == Qt.LeftButton:
        if True:
            # 弹出文件选择对话框
            file_path, _ = QFileDialog.getOpenFileName(self, "Select Image", "", "Image Files (*.jpg)")
            if file_path:
                # 读取新图片数据
                with open(file_path, "rb") as file:
                    image_data = file.read()
                # 将新图片显示在图片组件中
                self.picdata = image_data

                img = QImage()
                img.loadFromData(image_data)
                img_scaled = img.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                pixmap = QPixmap(img_scaled)
                self.cover_label.setPixmap(pixmap)

                pic_len = len(self.picdata)
                self.file_size_label.setText(f"File Size: {format_size(pic_len)} ({pic_len})")
                self.resolution_label.setText(f"Resolution: {img.size().width()}x{img.size().height()}")

                self.width_edit.setText(str(img.size().width()))
                self.height_edit.setText(str(img.size().height()))
                self.depth_edit.setText(str(img.depth()))


def format_size(size_bytes):
    """Convert bytes to a human-readable format."""
    if size_bytes == 0:
        return "0 B"
    # 定义单位和对应的字节大小
    units = ["B", "KB", "MB", "GB", "TB"]
    unit_index = 0
    # 从字节单位开始逐级增加
    while size_bytes >= 1024 and unit_index < len(units) - 1:
        size_bytes /= 1024
        unit_index += 1
    # 格式化输出结果，保留两位小数
    return "{:.2f} {}".format(size_bytes, units[unit_index])


class BlocksWindow(QDialog):
    def __init__(self, flac_path):
        super().__init__()
        self.resize(600, 400)
        self.setWindowTitle("FLAC Metadata Blocks")
        self.flac_path = flac_path
        self.blocks_table = TableWidgetDragRows()
        self.blocks_table.setColumnCount(2)
        self.blocks_table.setHorizontalHeaderLabels(["Block Code", "Block Type"])
        self.blocks_table.setColumnWidth(0, 150)
        self.blocks_table.setColumnWidth(1, 300)

        layout = QVBoxLayout()
        layout.addWidget(self.blocks_table)

        self.details_button = QPushButton("Details")
        self.delete_button = QPushButton("Delete")
        self.save_button = QPushButton("Save")
        self.close_button = QPushButton("Close")

        layout = QVBoxLayout()
        layout.addWidget(self.blocks_table)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.details_button)
        button_layout.addWidget(self.delete_button)
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.close_button)

        layout.addLayout(button_layout)

        self.setLayout(layout)

        self.loadMetadataBlocks()

        # 按钮绑定事件
        self.delete_button.clicked.connect(self.deleteBlock)
        self.details_button.clicked.connect(self.showBlockDetails)
        self.save_button.clicked.connect(self.saveBlocks)
        self.close_button.clicked.connect(self.close)

        self.blocks_table.setEditTriggers(QTableWidget.NoEditTriggers)

    def loadMetadataBlocks(self):
        if not self.flac_path:
            return
        try:
            flac = FLAC(self.flac_path)
            block_types = {
                0: 'STREAMINFO',
                1: 'PADDING',
                2: 'APPLICATION',
                3: 'SEEKTABLE',
                4: 'VORBIS COMMENT',
                6: 'PICTURE'
            }
            for i, block in enumerate(flac.metadata_blocks):
                block_type = block_types.get(block.code, "Unknown")
                # block_data = str(block)

                self.blocks_table.insertRow(self.blocks_table.rowCount())
                self.blocks_table.setItem(i, 0, QTableWidgetItem(str(block.code)))
                self.blocks_table.setItem(i, 1, QTableWidgetItem(block_type))

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error loading metadata blocks: {e}")

    def deleteBlock(self):
        # 删除块信息的事件处理程序
        # 获取选中的行
        selected_row = self.blocks_table.currentRow()
        if selected_row != -1:
            # 获取选中行的块代码
            block_code_item = self.blocks_table.item(selected_row, 0)
            block_code = int(block_code_item.text())
            if block_code == 0:
                # 如果块代码为0，提示不允许删除
                QMessageBox.warning(self, "Warning", "Streaminfo block cannot be deleted.")
            else:
                # 如果块代码不是0，弹出询问框确认删除
                reply = QMessageBox.question(self, "Confirmation", "Are you sure you want to delete this block?",
                                             QMessageBox.Yes | QMessageBox.No)
                if reply == QMessageBox.Yes:
                    # 用户确认删除，删除选中的行
                    self.blocks_table.removeRow(selected_row)
        else:
            QMessageBox.warning(self, "Warning", "Please select a block to delete.")

    def showBlockDetails(self):
        # 编辑块信息的事件处理程序
        # 获取选中的行
        selected_row = self.blocks_table.currentRow()
        if selected_row != -1:
            # 获取选中行的块代码
            block_code_item = self.blocks_table.item(selected_row, 0)
            block_code = int(block_code_item.text())
            if block_code == 6:
                cover_window = CoverWindow(self.flac_path)
                cover_window.exec_()
            elif block_code == 0:
                info_window = InfoWindow(self.flac_path)
                info_window.exec_()
            else:
                # 如果块代码为其他，弹出消息框提示该块代码
                QMessageBox.critical(self, "Error", f"No support for showing details of this block, block code is: {block_code}")
        else:
            QMessageBox.warning(self, "Warning", "Please select a block.")

    def saveBlocks(self):
        # 保存块信息的事件处理程序
        block_codes = []
        # 遍历表格的每一行
        for row in range(self.blocks_table.rowCount()):
            # 获取当前行的第一列，即块代码
            block_code_item = self.blocks_table.item(row, 0)
            if block_code_item:
                # 如果获取到了块代码，将其转换为整数并添加到列表中
                block_code = int(block_code_item.text())
                block_codes.append(block_code)
        # 打印块代码列表
        QMessageBox.information(self, "", f"{block_codes}")


class InfoWindow(QDialog):
    def __init__(self, flac_path):
        super().__init__()

        self.flac_path = flac_path

        self.setWindowTitle(f"{os.path.basename(flac_path)}")
        self.resize(500, 300)

        # Create layout
        layout = QGridLayout()

        # Add QLabel and QLineEdit for each property

        self.file_hash_label = QLabel("File Hash:")
        self.file_hash_edit = QLineEdit()
        self.file_hash_edit.setReadOnly(True)  # Read-only
        layout.addWidget(self.file_hash_label, 0, 0)
        layout.addWidget(self.file_hash_edit, 0, 1)

        self.md5_label = QLabel("Audio MD5:")
        self.md5_edit = QLineEdit()
        self.md5_edit.setReadOnly(False)
        layout.addWidget(self.md5_label, 1, 0)
        layout.addWidget(self.md5_edit, 1, 1)

        self.bits_per_sample_label = QLabel("Bits Per Sample:")
        self.bits_per_sample_edit = QLineEdit()
        self.bits_per_sample_edit.setReadOnly(True)  # Read-only
        layout.addWidget(self.bits_per_sample_label, 2, 0)
        layout.addWidget(self.bits_per_sample_edit, 2, 1)

        self.sample_rate_label = QLabel("Sample Rate:")
        self.sample_rate_edit = QLineEdit()
        self.sample_rate_edit.setReadOnly(True)  # Read-only
        layout.addWidget(self.sample_rate_label, 3, 0)
        layout.addWidget(self.sample_rate_edit, 3, 1)

        self.bit_rate_label = QLabel("Bit Rate:")
        self.bit_rate_edit = QLineEdit()
        self.bit_rate_edit.setReadOnly(True)  # Read-only
        layout.addWidget(self.bit_rate_label, 4, 0)
        layout.addWidget(self.bit_rate_edit, 4, 1)

        self.length_label = QLabel("Length:")
        self.length_edit = QLineEdit()
        self.length_edit.setReadOnly(True)  # Read-only
        layout.addWidget(self.length_label, 5, 0)
        layout.addWidget(self.length_edit, 5, 1)

        self.padding_length_label = QLabel("Padding Length:")
        self.padding_length_edit = QLineEdit()
        self.padding_length_edit.setReadOnly(True)  # Read-only
        layout.addWidget(self.padding_length_label, 6, 0)
        layout.addWidget(self.padding_length_edit, 6, 1)

        self.vendor_string_label = QLabel("Vendor String:")
        self.vendor_string_edit = QLineEdit()
        self.vendor_string_edit.setReadOnly(False)
        layout.addWidget(self.vendor_string_label, 7, 0)
        layout.addWidget(self.vendor_string_edit, 7, 1)

        # Add OK and Cancel buttons
        ok_button = QPushButton("Save")
        cancel_button = QPushButton("Cancel")
        # 创建按钮布局
        button_layout = QHBoxLayout()
        button_layout.addWidget(ok_button)
        button_layout.addWidget(cancel_button)

        ok_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
        layout.addLayout(button_layout, 9, 0, 1, 2)

        self.setLayout(layout)

        # Get FLAC file information
        self.showFLACInfo()

    def getFLACInfo(self, filepath):
        """Get information about the FLAC file.

        Args:
            filepath (str): The path to the FLAC file.

        Returns:
            tuple: A tuple containing file hash, MD5 signature, bits per sample, sample rate,
                bitrate, length, padding length, and vendor string.
        """
        try:
            # Calculate file hash
            file_hash = get_hash(filepath)

            # Read FLAC file
            flac = FLAC(filepath)
            info = flac.info

            # Get FLAC file information
            md5 = hex(info.md5_signature).split('x')[-1]
            sample_rate = f"{info.sample_rate / 1000} kHz"
            bits_per_sample = f"{info.bits_per_sample} bit"
            bitrate = f"{bits_per_second_to_kbps(info.bitrate)} kbps"
            length = format_seconds(info.length)

            # Get padding length
            padding_length = next((block.length for block in flac.metadata_blocks if block.code == 1), '')

            # Get vendor string
            vendor_string = flac.tags.vendor

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to read FLAC information: {str(e)}")
            return '', '', '', '', '', '', '', ''

        # Return FLAC information
        return file_hash, md5, bits_per_sample, sample_rate, bitrate, length, padding_length, vendor_string

    def showFLACInfo(self):
        try:
            # Get FLAC information
            file_hash, md5, bits_per_sample, sample_rate, bitrate, length, padding_length, vendor_string = self.getFLACInfo(
                self.flac_path)

            # Update the corresponding QLineEdit widgets
            self.file_hash_edit.setText(file_hash)
            self.md5_edit.setText(md5)
            self.bits_per_sample_edit.setText(str(bits_per_sample))
            self.sample_rate_edit.setText(str(sample_rate))
            self.bit_rate_edit.setText(str(bitrate))
            self.length_edit.setText(str(length))
            self.padding_length_edit.setText(str(padding_length))
            self.vendor_string_edit.setText(vendor_string)

        except Exception as e:
            print(f"Error loading FLAC information: {e}")


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = FLACTagEditor()
    window.show()
    sys.exit(app.exec_())
