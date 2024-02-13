import datetime
import hashlib
import os
import sys
from collections import Counter

from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QDropEvent, QBrush, QColor
from PyQt5.QtWidgets import QAbstractItemView, QApplication, QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, \
    QHeaderView, QListWidget, QPushButton, QFileDialog, QMessageBox, QDesktopWidget, QHBoxLayout, \
    QLineEdit, QCheckBox
from mutagen import File
from mutagen.flac import FLAC


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

        # Create a button for showing FLAC file info.
        self.info_button = QPushButton('Show FLAC Info', self)
        self.info_button.clicked.connect(self.showFLACInfo)

        # Create a button for deleting selected files.
        self.delete_button = QPushButton('Delete', self)
        self.delete_button.clicked.connect(self.deleteSelectedFiles)
        # self.delete_button.setEnabled(False)  # Initially disable the delete button.

        # Create a button for clearing the list.
        self.clear_button = QPushButton('Clear', self)
        self.clear_button.clicked.connect(self.clearList)

        # Create a horizontal layout for buttons.
        top_buttons_layout = QHBoxLayout()
        top_buttons_layout.addWidget(self.import_button)
        top_buttons_layout.addWidget(self.info_button)
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
        self.table.setColumnWidth(0, 150)
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

    def showFLACInfo(self):
        """Show information about the selected FLAC file."""

        selected_items = self.list_widget.selectedItems()
        if selected_items:
            filepath = selected_items[0].text()

            # Get FLAC file information
            file_hash, md5, bits_per_sample, sample_rate, bitrate, length, padding_length, vendor_string = self.getFLACInfo(
                filepath)

            # Construct the message to display
            msg_text = f'File Name: {os.path.basename(filepath)}\n' \
                       f'File Hash: {file_hash}\n' \
                       f'Audio MD5: {md5}\n' \
                       f'Bits Per Sample: {bits_per_sample} bit\n' \
                       f'Sample Rate: {sample_rate} kHz\n' \
                       f'Bit Rate: {bitrate} kbps\n' \
                       f'Length: {length}\n' \
                       f'Padding Length: {padding_length}\n' \
                       f'Vendor String: {vendor_string}\n'

            # Display the message in a QMessageBox
            msg = QMessageBox()
            msg.setWindowTitle("FLAC Information")
            msg.setText(msg_text)
            msg.exec_()
        else:
            QMessageBox.warning(self, "Warning", "Please select a FLAC file first.")

    def getFLACInfo(self, filepath):
        """Get information about the FLAC file.

        Args:
            filepath (str): The path to the FLAC file.

        Returns:
            tuple: A tuple containing file hash, MD5 signature, bits per sample, sample rate,
                bitrate, length, padding length, and vendor string.
        """

        # Initialize variables to store FLAC information
        file_hash = ''
        md5 = ''
        bits_per_sample = ''
        sample_rate = ''
        bitrate = ''
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
            bitrate = bits_per_second_to_kbps(info.bitrate)
            length = format_seconds(info.length)

            # Get padding length
            for block in flac.metadata_blocks:
                if block.code == 1:
                    padding_length = block.length

            # Get vendor string
            vendor_string = flac.tags.vendor

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to read FLAC information: {str(e)}")

        # Return FLAC information
        return file_hash, md5, bits_per_sample, sample_rate, bitrate, length, padding_length, vendor_string

    def deleteSelectedFiles(self):
        """Delete selected files from the list."""
        selected_items = self.list_widget.selectedItems()
        if selected_items:
            for item in selected_items:
                self.list_widget.takeItem(self.list_widget.row(item))
        else:
            QMessageBox.warning(self, "Warning", "Please select a FLAC file first.")
        # self.updateDeleteSelectedButtonState()

    # def updateDeleteSelectedButtonState(self):
    #     """Update the state of the delete button based on whether items are selected."""
    #     selected_items = self.list_widget.selectedItems()
    #     self.delete_button.setEnabled(bool(selected_items))

    def clearList(self):
        """Clear all items from the list."""
        # Clear the list
        self.list_widget.clear()
        # Update the state of the delete button
        # self.updateDeleteSelectedButtonState()  # 更新删除按钮状态

    def showTags(self):
        """Show tags of the selected FLAC file."""
        selected_items = self.list_widget.selectedItems()
        if selected_items:

            if len(selected_items) == 1:
                filepath = selected_items[0].text()
                try:
                    self.metadata = FLAC(filepath).tags
                    self.populateTable()
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to read tags from {filepath}: {str(e)}")
                    self.table.setRowCount(0)
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
                    QMessageBox.critical(self, "Error", "Selected files have different tag fields or orders.")
                    self.list_widget.clearSelection()
                    return

                # 清空表格并设置行数
                self.table.setRowCount(len(tag_fields[0]))

                # 填充表格
                for row, tag in enumerate(tag_fields[0]):
                    # 设置标签名称
                    field_item = QTableWidgetItem(tag)
                    self.table.setItem(row, 0, field_item)

                    # 获取所有文件中相同标签的值
                    values = []
                    for item in selected_items:
                        filepath = item.text()
                        flac = FLAC(filepath)
                        file_value = flac.tags.get(tag, [''])[0]
                        values.append(file_value)

                    # 检查所有值是否相同
                    if len(set(values)) == 1:
                        value_item = QTableWidgetItem(values[0])
                    else:
                        value_item = QTableWidgetItem("<Will Not Change>")
                        value_item.setForeground(QBrush(QColor(128, 128, 128)))  # 设置文本颜色为灰色

                    self.table.setItem(row, 1, value_item)


        else:
            self.table.setRowCount(0)

        # self.updateDeleteSelectedButtonState()

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

    # def saveFLAC(self):
    #     """Save metadata to a FLAC file."""
    #
    #     metadata_dict = {}
    #
    #     # Iterate over rows in the table
    #     for row in range(self.table.rowCount()):
    #         # Get the item in the "Field Name" column
    #         field_name_item = self.table.item(row, 0)
    #         # Get the item in the "Value" column
    #         value_item = self.table.item(row, 1)
    #         # If both items exist
    #         if field_name_item and value_item:
    #             # Get the text of the "Field Name" item
    #             field_name = field_name_item.text()
    #             # Get the text of the "Value" item
    #             value = value_item.text()
    #             # Add the field name and value to the metadata dictionary
    #             metadata_dict[field_name] = value
    #
    #     # Check if padding is enabled
    #     use_padding = self.use_padding_checkbox.isChecked()
    #
    #     # Check if padding is enabled and the padding value is valid
    #     if use_padding:
    #         padding_value = self.padding_lineedit.text()
    #         if not padding_value or not padding_value.isdigit():
    #             QMessageBox.critical(self, "Error",
    #                                  "Padding value must be a non-empty number when 'Use New Padding' is checked.")
    #             return
    #
    #     # Get selected items from the list widget
    #     selected_items = self.list_widget.selectedItems()
    #     if selected_items:
    #         # Get the filepath of the selected item
    #         filepath = selected_items[0].text()
    #         try:
    #             # Open the FLAC file
    #             flac = File(filepath)
    #
    #             # Clear existing tags
    #             if flac.tags:
    #                 flac.tags.clear()
    #
    #             # Set metadata tags
    #             for k, v in metadata_dict.items():
    #                 flac[k] = v
    #
    #             if use_padding:
    #                 # Save FLAC file with new padding
    #                 flac.save(padding=self.new_padding)
    #             else:
    #                 # Save FLAC file without new padding
    #                 flac.save()
    #             # Display success message
    #             QMessageBox.information(self, "Success", "Tags saved successfully.")
    #         except Exception as e:
    #             QMessageBox.critical(self, "Error", f"Failed to save tags to {filepath}: {str(e)}")
    #             self.table.setRowCount(0)  # Clear the table
    #             return
    #     else:
    #         QMessageBox.warning(self, "Warning", "Please select a FLAC file first.")
    #         return

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
                        # Only update tags with values that are not "<Will Not Change>"
                        if v == "<Will Not Change>":
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


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = FLACTagEditor()
    window.show()
    sys.exit(app.exec_())
