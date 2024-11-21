import datetime
import hashlib
import json
import os
import sys
import traceback

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

        # Enable multiple selection.
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
                # Check if the file path corresponds to a directory.
                if os.path.isdir(filepath):
                    # Recursively add all FLAC file paths from the directory to the list.
                    self.addFLACFilesFromDirectory(filepath)
                # Check if the file path corresponds to a FLAC file.
                elif self.parent().isFLAC(filepath):
                    # Add the file path to the list.
                    self.addItem(filepath)
                else:
                    print(f"{filepath} is not a directory or a FLAC file. Skipping.")
            self.sortItems()
            # Accept the proposed action.
            event.acceptProposedAction()

    def addFLACFilesFromDirectory(self, directory):
        """Recursively add FLAC file paths from the specified directory and its subdirectories."""
        # Iterate through all files and directories in the specified directory.
        for root, _, files in os.walk(directory):
            # Iterate through the files.
            for file in files:
                # Check if the file is a FLAC file.
                if self.parent().isFLAC(file):
                    # Construct the full file path.
                    filepath = os.path.join(root, file)
                    # Add the file path to the list.
                    self.addItem(filepath)


class FLACTagEditor(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):

        # Set the window title.
        self.setWindowTitle('FLAC Tag Editor')

        # Set the window's geometry (x, y, width, height).
        self.setGeometry(100, 100, 800, 600)

        # Center the window.
        self.center()

        # Create a button for importing FLAC files.
        self.import_button = QPushButton('Import FLAC Files', self)
        self.import_button.clicked.connect(self.importFLAC)

        # Create a button for showing metadata blocks.
        self.show_blocks_button = QPushButton("Show Metadata Blocks", self)
        self.show_blocks_button.clicked.connect(self.showBlocks)

        # Create a button for deleting selected files.
        self.delete_button = QPushButton('Delete', self)
        self.delete_button.clicked.connect(self.deleteSelectedFiles)

        # Create a button for clearing the list.
        self.clear_button = QPushButton('Clear', self)
        self.clear_button.clicked.connect(self.clearList)

        # Create a horizontal layout for buttons.
        top_buttons_layout = QHBoxLayout()
        top_buttons_layout.addWidget(self.import_button)
        top_buttons_layout.addWidget(self.show_blocks_button)
        top_buttons_layout.addWidget(self.delete_button)
        top_buttons_layout.addWidget(self.clear_button)

        # Create a drop list widget.
        self.list_widget = DropList(self)
        # Enable accepting drops.
        self.list_widget.setAcceptDrops(True)
        # Set the fixed height of the list widget.
        self.list_widget.setFixedHeight(150)
        self.list_widget.itemSelectionChanged.connect(self.showTags)

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

        self.cover_button = QPushButton('Set Cover', self)
        self.cover_button.clicked.connect(self.setCover)

        # Create a button for saving changes.
        self.save_button = QPushButton('Save', self)
        self.save_button.clicked.connect(self.saveFLAC)

        # Create a checkbox for padding.
        self.use_padding_checkbox = QCheckBox('Use New Padding', self)
        self.use_padding_checkbox.stateChanged.connect(self.updatePaddingLineEditState)
        # Create a line edit for entering padding value.
        self.padding_lineedit = QLineEdit(self)
        # Set placeholder text for the line edit.
        self.padding_lineedit.setPlaceholderText("Enter padding value")
        # Initially disable the line edit.
        self.padding_lineedit.setEnabled(False)

        # Create a horizontal layout for add and delete buttons.
        buttons_layout_left = QHBoxLayout()
        buttons_layout_left.addWidget(self.add_button)
        buttons_layout_left.addWidget(self.delete_button)
        buttons_layout_left.addWidget(self.cover_button)

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

        # If executed from the command line with file path arguments,
        # add the files to the list
        if len(sys.argv) > 1:
            file_paths = sys.argv[1:]
            for file_path in file_paths:
                if self.isFLAC(file_path):
                    self.list_widget.addItem(file_path)
                else:
                    print(f"{file_path} is not a FLAC file. Skipping.")

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


    def setCover(self):
        selected_items = self.list_widget.selectedItems()
        if selected_items:
            # Create a list to store the text of selected items
            selected_paths = []

            # Add the text of selected items to the list
            for item in selected_items:
                selected_paths.append(item.text())

            cover_window = CoverWindow(selected_paths)
            cover_window.exec_()

            #
            # # If a single file is selected
            # if len(selected_items) == 1:
            #     filepath = selected_items[0].text()
            #     cover_window = CoverWindow(filepath)
            #     cover_window.exec_()

            # else:
            #     QMessageBox.critical(self, "Error", "Batch set cover is not supported.")

        else:
            QMessageBox.critical(self, "Error", "Please select a FLAC file first.")




    def showBlocks(self):
        """
        Show the BlocksWindow dialog with the selected FLAC files.

        This method is triggered when the user clicks on a button to show the BlocksWindow dialog.
        It gathers the selected FLAC file paths from the list widget and passes them to the BlocksWindow dialog.

        """
        # Get the selected items from the list widget
        selected_items = self.list_widget.selectedItems()
        if selected_items:
            # Create a list to store the text of selected items
            selected_paths = []

            # Add the text of selected items to the list
            for item in selected_items:
                selected_paths.append(item.text())

            # Create and execute a BlocksWindow with the selected paths
            cover_window = BlocksWindow(selected_paths)
            cover_window.exec_()
        else:
            # Show a warning if no FLAC file is selected
            QMessageBox.warning(self, "Warning", "Please select a FLAC file first.")

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
        """
        Show tags of the selected FLAC files.

        If a single file is selected, this method reads the tags of that file and populates the table with tag information.
        If multiple files are selected, it checks if they have the same tag fields and orders. If they do, it populates the table
        with tag values. If not, it displays an error message.

        """
        selected_items = self.list_widget.selectedItems()
        if selected_items:

            # If a single file is selected
            if len(selected_items) == 1:
                filepath = selected_items[0].text()
                try:
                    metadata = FLAC(filepath).tags

                    # Set the number of rows in the table
                    self.table.setRowCount(len(metadata))

                    # Initialize the row index
                    row = 0

                    # Iterate through metadata items
                    for key, value in metadata:
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
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to read tags from {filepath}: {str(e)}")
                    self.table.setRowCount(0)
            # If multiple files are selected
            else:
                # List to store tag fields and their orders for each selected file
                tag_fields = []

                # Iterate through selected files to get tag fields and orders for each file
                for item in selected_items:
                    filepath = item.text()
                    flac = FLAC(filepath)
                    tag_fields.append([key for key, _ in flac.tags])

                # Check if tag fields lists are identical (including order)
                is_same_tags = all(tag_fields[0] == tag_list for tag_list in tag_fields)

                if not is_same_tags:
                    self.table.setRowCount(0)
                    QMessageBox.critical(self, "Error", "Selected files have different tag fields or orders.")
                    return

                # Clear the table and set the row count
                self.table.setRowCount(len(tag_fields[0]))

                # Populate the table
                for row, tag in enumerate(tag_fields[0]):
                    # Set the tag name
                    field_item = QTableWidgetItem(tag)
                    self.table.setItem(row, 0, field_item)

                    # Get values for the same tag across all selected files
                    values = set()
                    for item in selected_items:
                        filepath = item.text()
                        flac = FLAC(filepath)
                        file_value = flac.tags.get(tag, [''])[0]
                        values.add(file_value)

                    if len(values) == 1:
                        value_item = QTableWidgetItem(next(iter(values)))
                    else:
                        # Sort the values
                        # sorted_values = sorted(values, key=custom_sort)
                        sorted_values = sorted(values)

                        # Concatenate sorted values into a string
                        text = "; ".join(sorted_values)
                        value_item = QTableWidgetItem(f"≪Multivalued≫ {text}")
                        self.table.setItem(row, 1, value_item)

                        # Set text color to gray
                        value_item.setForeground(QBrush(QColor(128, 128, 128)))

                    self.table.setItem(row, 1, value_item)
        else:
            self.table.setRowCount(0)

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
            self.table.scrollToItem(item, QtWidgets.QAbstractItemView.PositionAtTop)

    def deleteTableRow(self):
        """Delete selected rows from the table."""

        # Get selected rows
        selected_rows = self.table.selectionModel().selectedRows()

        if not selected_rows:
            QMessageBox.critical(self, "Error", "Please select a row.")
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

            # Iterate over selected files
            for item in selected_items:

                filepath = item.text()

                try:
                    flac = File(filepath)

                    # Clear existing tags
                    if flac.tags:
                        flac.tags.clear()

                    # Set metadata tags
                    for k, v in metadata_dict.items():
                        if v.startswith("≪Multivalued≫ "):
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
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to save tags to {filepath}: {str(e)}")
                    return

            # Display success message
            QMessageBox.information(self, "Success", "Tags saved successfully.")

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


class BlocksWindow(QDialog):
    def __init__(self, flac_path):
        super().__init__()
        self.resize(600, 400)
        self.setWindowTitle("FLAC Metadata Blocks")
        self.flac_path = flac_path
        self.blocks_table = TableWidgetDragRows()
        self.blocks_table.setColumnCount(4)
        self.blocks_table.setHorizontalHeaderLabels(["Block Code", "Block Type", "Block Data", "Hash"])
        self.blocks_table.setColumnWidth(0, 100)
        self.blocks_table.setColumnWidth(1, 150)
        self.blocks_table.setColumnWidth(2, 500)
        self.blocks_table.setColumnWidth(3, 200)

        layout = QVBoxLayout()
        layout.addWidget(self.blocks_table)

        self.details_button = QPushButton("Details")
        # self.add_button = QPushButton("Add")
        self.delete_button = QPushButton("Delete")
        self.save_button = QPushButton("Save")
        self.close_button = QPushButton("Close")

        layout = QVBoxLayout()
        layout.addWidget(self.blocks_table)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.details_button)
        # button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.delete_button)
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.close_button)

        layout.addLayout(button_layout)

        self.setLayout(layout)

        self.block_types = {
            0: 'STREAMINFO',
            1: 'PADDING',
            2: 'APPLICATION',
            3: 'SEEKTABLE',
            4: 'VORBIS COMMENT',
            6: 'PICTURE'
        }

        self.loadMetadataBlocks()

        self.delete_button.clicked.connect(self.deleteBlock)
        # self.add_button.clicked.connect(self.addBlock)
        self.details_button.clicked.connect(self.showBlockDetails)
        self.save_button.clicked.connect(self.saveBlocks)
        self.close_button.clicked.connect(self.close)

        self.blocks_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.blocks_table.cellDoubleClicked.connect(self.showBlockDetails)

    def loadMetadataBlocks(self):
        """
        Load metadata blocks from FLAC files.

        This method ensures the consistency of metadata block counts and block codes among multiple FLAC files.

        Raises:
            QMessageBox.critical: If an error occurs during loading metadata blocks or if metadata block counts or
                block codes are inconsistent among FLAC files.
        """
        if not self.flac_path:
            return
        try:

            block_counts = []
            block_codes = []

            if len(self.flac_path) > 1:
                # Iterate over each FLAC file path
                for path in self.flac_path:
                    flac = FLAC(path)

                    # Get the number of metadata blocks in the current FLAC file
                    blocks_count = len(flac.metadata_blocks)
                    # Add the number of metadata blocks to the list
                    block_counts.append(blocks_count)
                    # Get the metadata block code list
                    block_code = [block.code for block in flac.metadata_blocks]
                    # Add the metadata block code list to the list
                    block_codes.append(block_code)

                # Check if all values in the metadata block count list are the same
                if len(set(block_counts)) != 1:
                    QMessageBox.critical(window, "Error", "Metadata blocks count is not consistent among FLAC files.")
                    return

                # Check if all values in the metadata block code list are the same
                if len(set(map(tuple, block_codes))) != 1:
                    QMessageBox.critical(window, "Error",
                                         "Metadata block codes combination is not consistent among FLAC files.")
                    return

            flac = FLAC(self.flac_path[0])

            for i, block in enumerate(flac.metadata_blocks):
                block_type = self.block_types.get(block.code, "Unknown")
                self.blocks_table.insertRow(self.blocks_table.rowCount())
                self.blocks_table.setItem(i, 0, QTableWidgetItem(str(block.code)))
                self.blocks_table.setItem(i, 1, QTableWidgetItem(block_type))
                block_data = str(vars(block) if block.code != 6 else block)
                self.blocks_table.setItem(i, 2, QTableWidgetItem(block_data))

                block_data_hash = hash_data(block_data)
                self.blocks_table.setItem(i, 3, QTableWidgetItem(block_data_hash))


        except Exception as e:
            QMessageBox.critical(window, "Error", f"Error loading metadata blocks: {e}")


    # def addBlock(self):




    def deleteBlock(self):
        """
        Delete selected metadata blocks.

        This method allows the user to delete selected metadata blocks from the table. It prevents the deletion of
        STREAMINFO blocks.

        Raises:
            QMessageBox.critical: If no block is selected.
            QMessageBox.warning: If the selected block is STREAMINFO, which cannot be deleted.
            QMessageBox.question: Asks for confirmation before deleting a block.
        """

        selected_rows = self.blocks_table.selectionModel().selectedRows()

        if not selected_rows:
            QMessageBox.critical(self, "Error", "Please select a block.")
            return

        rows_to_delete = []

        for row in selected_rows:
            block_code_item = self.blocks_table.item(row.row(), 0)
            if block_code_item:

                block_code = int(block_code_item.text())
                if block_code == 0:
                    # If the block code is 0, prompt that deletion is not allowed
                    QMessageBox.warning(self, "Warning", f"{self.block_types.get(block_code)} block cannot be deleted.")
                else:
                    # If the block code is not 0, prompt for confirmation before deletion
                    reply = QMessageBox.question(self, "Confirmation",
                                                 f"Are you sure you want to delete {self.block_types.get(block_code)} block?",
                                                 QMessageBox.Yes | QMessageBox.No)
                    if reply == QMessageBox.Yes:
                        # If the block code is not 0, add the row to the list of rows to delete
                        rows_to_delete.append(row.row())

        # Remove the selected rows in reverse order to avoid index issues
        for row_index in reversed(rows_to_delete):
            self.blocks_table.removeRow(row_index)

    def showBlockDetails(self):
        """
        Show details of the selected metadata block.

        This method displays detailed information about the selected metadata block when triggered by the user.

        Raises:
            QMessageBox.critical: If no block is selected or if the block code is not supported.
        """
        selected_rows = self.blocks_table.selectionModel().selectedRows()

        if not selected_rows:
            QMessageBox.critical(self, "Error", "Please select a block.")
            return

        for row in selected_rows:
            # Get the block code of the current row
            block_code_item = self.blocks_table.item(row.row(), 0)
            block_code = int(block_code_item.text())
            if block_code == 6:
                cover_window = CoverWindow(self.flac_path)
                cover_window.exec_()
            elif block_code == 0:
                info_window = InfoWindow(self.flac_path)
                info_window.exec_()
            else:
                block_data_text = self.blocks_table.item(row.row(), 2).text()
                QMessageBox.information(self, "Block Information", block_data_text)
                # If the block code is not supported, display an error message
                # QMessageBox.critical(self, "Error",
                #                      f"No support for showing details of {self.block_types.get(block_code)} block.")

    def saveBlocks(self):
        """
        Save metadata blocks based on the reordered block codes.

        This method saves the reordered metadata blocks based on the new block codes obtained from the table.

        Raises:
            QMessageBox.warning: If the last block is not PADDING, indicating potential issues with the modification.
            QMessageBox.information: Upon successful modification.
        """
        new_block_codes = []
        new_block_data_hash = []

        # Iterate over each row in the table
        for row in range(self.blocks_table.rowCount()):
            # Get the block code of the current row, which is the first column
            block_code_item = self.blocks_table.item(row, 0)

            block_data_hash = self.blocks_table.item(row, 3).text()

            if block_code_item:
                # If a block code is obtained, convert it to an integer and add it to the list
                old_block_codes = int(block_code_item.text())
                new_block_codes.append(old_block_codes)

                new_block_data_hash.append(block_data_hash)

        print(f"new_block_codes={new_block_codes}")
        print(f"new_block_data_hash={new_block_data_hash}")

        # Iterate over each FLAC file path
        for path in self.flac_path:
            flac = FLAC(path)
            # Create a backup of the metadata blocks
            bak = flac.metadata_blocks[:]
            # Clear the original metadata blocks
            flac.metadata_blocks.clear()

            # Reinsert metadata blocks based on the new order
            for new_index, block_code_value in enumerate(new_block_codes):
                # Find the metadata block corresponding to the current block code value in the backup

                # 2024-05-27 同时判断block编号和block数据str的hash都相同的情况下才会移动
                elm = next((block for block in bak if block.code == block_code_value and new_block_data_hash[new_index] == hash_data(str(vars(block) if block.code != 6 else block))), None)
                flac.metadata_blocks.insert(new_index, elm)
            # Save the modified FLAC file
            flac.save()
        self.blocks_table.setRowCount(0)
        self.loadMetadataBlocks()

        # Get the new block codes list
        new_block_codes = [block.code for block in FLAC(self.flac_path[0]).metadata_blocks]

        # Check if the last block is PADDING
        if new_block_codes[-1] != 1:
            QMessageBox.warning(self, "Warning",
                                "Modification completed, changes to PADDING may not take effect, PADDING must be at the last position.")
        else:
            QMessageBox.information(self, "Success", "Modification completed")


class InfoWindow(QDialog):
    def __init__(self, flac_path):
        super().__init__()

        if flac_path:
            self.flac_path = flac_path
        else:
            return

        if len(self.flac_path) == 1:
            self.setWindowTitle(f"{os.path.basename(self.flac_path[0])}")
        else:
            first_file = os.path.basename(self.flac_path[0])
            remaining_files_count = len(self.flac_path) - 1
            self.setWindowTitle(f"{first_file} and {remaining_files_count} more files")

        self.resize(500, 300)

        # Create layout
        layout = QGridLayout()

        self.file_length_label = QLabel("File Length:")
        self.file_length_edit = QLineEdit()
        self.file_length_edit.setReadOnly(True)
        layout.addWidget(self.file_length_label, 0, 0)
        layout.addWidget(self.file_length_edit, 0, 1)

        # Add QLabel and QLineEdit for each property
        self.file_hash_label = QLabel("File Hash:")
        self.file_hash_edit = QLineEdit()
        self.file_hash_edit.setReadOnly(True)  # Read-only
        layout.addWidget(self.file_hash_label, 1, 0)
        layout.addWidget(self.file_hash_edit, 1, 1)

        self.md5_label = QLabel("Audio MD5:")
        self.md5_edit = QLineEdit()
        self.md5_edit.setReadOnly(False)
        layout.addWidget(self.md5_label, 2, 0)
        layout.addWidget(self.md5_edit, 2, 1)

        self.length_label = QLabel("Length:")
        self.length_edit = QLineEdit()
        self.length_edit.setReadOnly(True)
        layout.addWidget(self.length_label, 3, 0)
        layout.addWidget(self.length_edit, 3, 1)

        self.bits_per_sample_label = QLabel("Bits Per Sample:")
        self.bits_per_sample_edit = QLineEdit()
        self.bits_per_sample_edit.setReadOnly(True)
        layout.addWidget(self.bits_per_sample_label, 4, 0)
        layout.addWidget(self.bits_per_sample_edit, 4, 1)

        self.sample_rate_label = QLabel("Sample Rate:")
        self.sample_rate_edit = QLineEdit()
        self.sample_rate_edit.setReadOnly(True)
        layout.addWidget(self.sample_rate_label, 5, 0)
        layout.addWidget(self.sample_rate_edit, 5, 1)

        self.bit_rate_label = QLabel("Bit Rate:")
        self.bit_rate_edit = QLineEdit()
        self.bit_rate_edit.setReadOnly(True)
        layout.addWidget(self.bit_rate_label, 6, 0)
        layout.addWidget(self.bit_rate_edit, 6, 1)

        self.vendor_string_label = QLabel("Vendor String:")
        self.vendor_string_edit = QLineEdit()
        self.vendor_string_edit.setReadOnly(False)
        layout.addWidget(self.vendor_string_label, 7, 0)
        layout.addWidget(self.vendor_string_edit, 7, 1)

        self.padding_length_label = QLabel("Padding Length:")
        self.padding_length_edit = QLineEdit()
        self.padding_length_edit.setReadOnly(True)
        layout.addWidget(self.padding_length_label, 8, 0)
        layout.addWidget(self.padding_length_edit, 8, 1)

        self.max_blocksize_label = QLabel("Maximum Blocksize:")
        self.max_blocksize_edit = QLineEdit()
        self.max_blocksize_edit.setReadOnly(True)
        layout.addWidget(self.max_blocksize_label, 9, 0)
        layout.addWidget(self.max_blocksize_edit, 9, 1)

        self.min_blocksize_label = QLabel("Minimum Blocksize:")
        self.min_blocksize_edit = QLineEdit()
        self.min_blocksize_edit.setReadOnly(True)
        layout.addWidget(self.min_blocksize_label, 10, 0)
        layout.addWidget(self.min_blocksize_edit, 10, 1)

        self.max_framesize_label = QLabel("Maximum Framesize:")
        self.max_framesize_edit = QLineEdit()
        self.max_framesize_edit.setReadOnly(True)
        layout.addWidget(self.max_framesize_label, 11, 0)
        layout.addWidget(self.max_framesize_edit, 11, 1)

        self.min_framesize_label = QLabel("Minimum Framesize:")
        self.min_framesize_edit = QLineEdit()
        self.min_framesize_edit.setReadOnly(True)
        layout.addWidget(self.min_framesize_label, 12, 0)
        layout.addWidget(self.min_framesize_edit, 12, 1)

        self.total_samples_label = QLabel("Total Samples:")
        self.total_samples_edit = QLineEdit()
        self.total_samples_edit.setReadOnly(True)
        layout.addWidget(self.total_samples_label, 13, 0)
        layout.addWidget(self.total_samples_edit, 13, 1)

        # Add OK and Cancel buttons
        ok_button = QPushButton("Save")
        cancel_button = QPushButton("Cancel")

        button_layout = QHBoxLayout()
        button_layout.addWidget(ok_button)
        button_layout.addWidget(cancel_button)

        ok_button.clicked.connect(self.save_info)
        cancel_button.clicked.connect(self.reject)
        layout.addLayout(button_layout, 14, 0, 1, 2)

        self.setLayout(layout)

        self.showFLACInfo()

    def save_info(self):
        """
        Save vendor and MD5 information to FLAC files.

        If the vendor or MD5 text fields start with "≪Multivalued≫", the values will be preserved from the FLAC file.
        """
        for path in self.flac_path:
            audio = FLAC(path)

            vendor = self.vendor_string_edit.text()
            md5 = self.md5_edit.text()

            # Check if the values from the text fields should be used
            if vendor.startswith("≪Multivalued≫"):
                vendor = audio.tags.vendor

            if md5.startswith("≪Multivalued≫"):
                decimal_value = audio.info.md5_signature
            else:
                # Convert hexadecimal string to decimal value
                decimal_value = int(md5, 16) if md5 else ""
            audio.tags.vendor = vendor
            audio.info.md5_signature = decimal_value

            audio.save()
        QMessageBox.information(self, "Success", "Modification completed")

    def getFLACInfo(self, filepath):
        # Initialize variables to store FLAC information
        flac_info = {
            'file_hash': '',
            'md5': '',
            'bits_per_sample': '',
            'sample_rate': '',
            'bitrate': '',
            'length': '',
            'padding_length': '',
            'vendor_string': '',
            'min_blocksize': '',
            'max_blocksize': '',
            'total_samples': '',
            'min_framesize': '',
            'max_framesize': '',
            'file_length': ''
        }

        try:
            file_len = os.path.getsize(filepath)
            flac_info['file_length'] = str(f'{file_len} ({format_size(file_len)})')

            # Calculate file hash
            flac_info['file_hash'] = str(get_hash(filepath))

            # Read FLAC file
            flac = FLAC(filepath)
            info = flac.info

            # Get FLAC file information
            try:
                if info.md5_signature:
                    flac_info['md5'] = str(hex(info.md5_signature).split('x')[-1])
            except Exception as e:
                print(f"Failed to read md5: {str(e)}")

            try:
                if info.length:
                    flac_info['length'] = str(format_seconds(info.length))
            except Exception as e:
                print(f"Failed to read length: {str(e)}")

            try:
                if info.sample_rate:
                    flac_info['sample_rate'] = f"{info.sample_rate / 1000} kHz"
            except Exception as e:
                print(f"Failed to read sample rate: {str(e)}")

            try:
                if info.bits_per_sample:
                    flac_info['bits_per_sample'] = f"{info.bits_per_sample} bit"
            except Exception as e:
                print(f"Failed to read bits per sample: {str(e)}")

            try:
                if info.bitrate:
                    flac_info['bitrate'] = f"{bits_per_second_to_kbps(info.bitrate)} kbps"
            except Exception as e:
                print(f"Failed to read bitrate: {str(e)}")

            try:
                if flac.tags:
                    flac_info['vendor_string'] = str(flac.tags.vendor)
            except Exception as e:
                print(f"Failed to read vendor string: {str(e)}")

            # Get padding length
            padding_block = next((block for block in flac.metadata_blocks if block.code == 1), None)
            if padding_block:
                flac_info['padding_length'] = str(padding_block.length)

            flac_info['max_blocksize'] = str(info.max_blocksize)
            flac_info['min_blocksize'] = str(info.min_blocksize)
            flac_info['max_framesize'] = str(info.max_framesize)
            flac_info['min_framesize'] = str(info.min_framesize)
            flac_info['total_samples'] = str(info.total_samples)

        except Exception as e:
            QMessageBox.critical(window, "Error", f"Failed to read FLAC information: {str(e)}")

        # Return FLAC information
        return flac_info

    def showFLACInfo(self):
        """
        Display FLAC file information in the corresponding QLineEdit widgets.

        If there is only one FLAC file selected, display its information.
        If multiple FLAC files are selected, display unique values across all files.
        """
        if not self.flac_path:
            return {}

        if len(self.flac_path) == 1:
            try:
                # Get FLAC information
                flac_info = self.getFLACInfo(self.flac_path[0])

                # Update the corresponding QLineEdit widgets
                self.updateLineEditWidgets(flac_info)

                return flac_info

            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error loading FLAC information: {e}")
                return {}
        else:
            try:
                # Get information for multiple FLAC files
                file_infos = []

                for flac_path in self.flac_path:
                    file_info = self.getFLACInfo(flac_path)
                    file_infos.append(file_info)

                # Merge information dictionaries
                merged_info = self.mergeFileInfo(file_infos)

                # Update the corresponding QLineEdit widgets
                self.updateLineEditWidgets(merged_info)

                return merged_info

            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error loading FLAC information: {e}")
                return {}

    def updateLineEditWidgets(self, flac_info):
        """
        Update the corresponding QLineEdit widgets with FLAC information.

        Args:
            flac_info (dict): Dictionary containing FLAC information.
        """
        self.file_hash_edit.setText(flac_info['file_hash'])
        self.md5_edit.setText(flac_info['md5'])
        self.bits_per_sample_edit.setText(flac_info['bits_per_sample'])
        self.sample_rate_edit.setText(flac_info['sample_rate'])
        self.bit_rate_edit.setText(flac_info['bitrate'])
        self.length_edit.setText(flac_info['length'])
        self.padding_length_edit.setText(flac_info['padding_length'])
        self.vendor_string_edit.setText(flac_info['vendor_string'])
        self.min_blocksize_edit.setText(flac_info['min_blocksize'])
        self.max_blocksize_edit.setText(flac_info['max_blocksize'])
        self.total_samples_edit.setText(flac_info['total_samples'])
        self.min_framesize_edit.setText(flac_info['min_framesize'])
        self.max_framesize_edit.setText(flac_info['max_framesize'])
        self.file_length_edit.setText(flac_info['file_length'])

    def mergeFileInfo(self, file_infos):
        """
        Merge information dictionaries for multiple FLAC files.

        Args:
            file_infos (list): List of dictionaries containing FLAC information for each file.

        Returns:
            dict: Merged dictionary containing unique values across all files.
        """
        merged_info = {}
        for key in file_infos[0].keys():
            values = [info[key] for info in file_infos]
            merged_info[key] = self.getUniqueValue(values)

        return merged_info

    def getUniqueValue(self, values):
        """
        Get a unique value from a list of values.

        Args:
            values (list): A list of values.

        Returns:
            str: A unique value from the list or "≪Multivalued≫" followed by semicolon-separated values if values are not identical.
        """
        # Check if all values in the list are the same
        if all(x == values[0] for x in values):
            return values[0]
        else:
            # If values are different, return "≪Multivalued≫" followed by semicolon-separated values
            return "≪Multivalued≫ " + "; ".join(set(values))


class CoverWindow(QDialog):
    def __init__(self, flac_path):
        super().__init__()

        self.resize(400, 400)  # Set the initial size of the window
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

        self.cover_label.mouseDoubleClickEvent = self.chooseImageDoubleClick

        # Create a context menu
        self.context_menu = QMenu(self)
        self.import_action = QAction("Import", self)
        self.export_action = QAction("Export", self)

        # Add actions to the context menu
        self.context_menu.addAction(self.import_action)
        self.context_menu.addAction(self.export_action)

        # Connect actions to their respective slots
        self.import_action.triggered.connect(self.chooseImage)
        self.export_action.triggered.connect(self.exportCover)

        # Install event filter on the image component
        self.cover_label.installEventFilter(self)
        # edit 2024.11.21
        self.picdata = None

    def eventFilter(self, source, event):
        """Event filter function to capture right-click events on the image component and display the context menu."""
        if source is self.cover_label and event.type() == QEvent.ContextMenu:
            # Display the context menu
            self.context_menu.exec_(event.globalPos())
            return True
        return super().eventFilter(source, event)

    def exportCover(self):
        """Export the cover image to a file."""
        if self.picdata is None:
            QMessageBox.information(self, "Error", "No cover image to save.")
            return
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Cover Image", "cover.jpg", "JPEG Files (*.jpg)")
        if file_path:
            # Save the image data to a file
            with open(file_path, 'wb') as f:
                f.write(self.picdata)
            QMessageBox.information(self, "Success", "Cover saved successfully.")

    def checkCoverConsistency(self, flac_paths):
        """
        Check the consistency of cover images across multiple FLAC files.

        Args:
            flac_paths (list of str): List of paths to the FLAC files.

        Returns:
            bool: True if all cover images are consistent, False otherwise.
        """
        first_pic_data = None
        for flac_path in flac_paths:
            try:
                audio = FLAC(flac_path)
                pictures = audio.pictures
                for p in pictures:
                    if p.type == 3:
                        if first_pic_data is None:
                            first_pic_data = p.data
                        elif first_pic_data != p.data:
                            return False
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error loading cover image: {e}")
                return False
        return True

    def showCoverImage(self, flac_paths):
        """
        Show the cover image for the given FLAC file(s).

        Args:
            flac_paths (list of str): List of paths to the FLAC file(s).
        """
        if not flac_paths:
            return
        try:
            # Check consistency of cover images if there are multiple files
            if len(flac_paths) > 1:
                if not self.checkCoverConsistency(flac_paths):
                    self.cover_label.setFixedHeight(200)
                    self.cover_label.setText("Multiple images")
                    return

            audio = FLAC(flac_paths[0])
            pictures = audio.pictures
            for p in pictures:
                if p.type == 3:
                    self.picdata = p.data
                    img = QImage()
                    img.loadFromData(p.data)
                    img_scaled = img.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
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
            # edit 2024.11.21
            self.cover_label.setFixedHeight(200)
            self.cover_label.setText("No cover")
            return
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error displaying cover image: {e}")
            return

    def saveTags(self):
        """
        Save tags and cover image for the FLAC file(s).
        """
        if not self.flac_path:
            return
        if not self.picdata:
            return

        if len(self.flac_path) > 1:
            # For multiple files, update cover image and save tags for each file
            picture = Picture()
            picture.type = 3
            picture.mime = 'image/jpeg'
            picture.data = self.picdata
            height_text = self.height_edit.text()
            width_text = self.width_edit.text()
            depth_text = self.depth_edit.text()
            try:
                height = int(height_text) if height_text else None
                width = int(width_text) if width_text else None
                depth = int(depth_text) if depth_text else None
            except ValueError:
                QMessageBox.critical(self, "Error", "Invalid input. Please enter valid numbers for height, width, "
                                                    "and depth.")
                return

            picture.width = width
            picture.height = height
            picture.depth = depth
            picture.desc = self.desc_edit.text()

            for path in self.flac_path:
                audio = FLAC(path)
                audio.clear_pictures()
                audio.add_picture(picture)
                audio.save()

            QMessageBox.information(self, "Success", "All tags saved successfully.")
        else:
            # For a single file, update cover image and save tags
            audio = FLAC(self.flac_path[0])
            picture = Picture()
            picture.type = 3
            picture.mime = 'image/jpeg'
            picture.data = self.picdata

            try:
                height_text = self.height_edit.text()
                width_text = self.width_edit.text()
                depth_text = self.depth_edit.text()

                # Convert text to integers or None if text is empty
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

    def chooseImageDoubleClick(self, event):
        """
        Event handler for double-click event on the image label.
        Opens the chooseImage method upon left mouse button double-click.
        """
        if event.button() == Qt.LeftButton:
            self.chooseImage()

    def chooseImage(self):
        """
        Opens a file dialog to select an image file, then displays the chosen image.
        """
        # Open a file dialog to select an image file
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Image", "", "Image Files (*.jpg)")
        if file_path:
            # Read the image data from the selected file
            with open(file_path, "rb") as file:
                image_data = file.read()

            # Display the selected image in the image label
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


def format_size(size_bytes):
    """
    Convert bytes to a human-readable format.

    Args:
        size_bytes (int): The size in bytes.

    Returns:
        str: A string representing the size in a human-readable format.
    """
    if size_bytes == 0:
        return "0 B"
    # Define units and their corresponding byte sizes
    units = ["B", "KB", "MB", "GB", "TB"]
    unit_index = 0
    # Increase gradually starting from byte unit
    while size_bytes >= 1024 and unit_index < len(units) - 1:
        size_bytes /= 1024
        unit_index += 1
    # Format the output result, keeping two decimal places
    return "{:.2f} {}".format(size_bytes, units[unit_index])


def bits_per_second_to_kbps(bits_per_second):
    """Convert bits per second to kilobits per second (kbps).

    Args:
        bits_per_second (int): Bits per second.

    Returns:
        str: The converted value in kilobits per second.
    """
    kbps = round(bits_per_second / 1000)
    return kbps


def custom_sort(value):
    """
    Custom sorting function that converts strings to integers for comparison.

    Args:
        value (str): The value to be sorted.

    Returns:
        int or str: The converted integer value if the input can be converted to an integer, otherwise the original string.
    """
    if value.isdigit():
        return int(value)
    else:
        return value


def hash_data(data):
    # 创建一个 SHA-256 哈希对象
    sha256 = hashlib.sha256()

    # 更新哈希对象，传入数据（需要是字节类型）
    sha256.update(data.encode('utf-8'))

    # 返回哈希值的十六进制表示
    return sha256.hexdigest()


def exception_hook(exc_type, exc_value, exc_traceback):
    """
    Custom exception hook to handle uncaught exceptions.
    """
    # 构建异常消息
    exception_message = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))

    # 显示异常消息框
    QMessageBox.critical(None, "Exception", exception_message, QMessageBox.StandardButton.Ok)
    sys.__excepthook__(exc_type, exc_value, exc_traceback)  # 继续执行默认的异常处理


if __name__ == '__main__':
    # 设置全局异常处理程序
    sys.excepthook = exception_hook

    app = QApplication(sys.argv)
    window = FLACTagEditor()
    window.show()
    sys.exit(app.exec_())
