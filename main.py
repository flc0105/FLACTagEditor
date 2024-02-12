import sys

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QDropEvent
from PyQt5.QtWidgets import QApplication, QWidget, QPushButton, QFileDialog, QVBoxLayout, QTableWidget, \
    QTableWidgetItem, QHeaderView, QAbstractItemView
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

    def initUI(self):
        self.setWindowTitle('FLAC Tag Editor')
        self.setGeometry(100, 100, 600, 400)

        self.import_button = QPushButton('Import FLAC File', self)
        self.import_button.clicked.connect(self.importFLAC)

        self.save_button = QPushButton('Save', self)
        self.save_button.clicked.connect(self.saveFLAC)

        self.table = TableWidgetDragRows(self)
        self.table.setColumnCount(2)
        self.table.verticalHeader().setVisible(False)
        self.table.setHorizontalHeaderLabels(['Field Name', 'Value'])
        self.table.setColumnWidth(0, 300)
        self.table.setColumnWidth(1, 300)

        layout = QVBoxLayout()
        layout.addWidget(self.import_button)
        layout.addWidget(self.table)
        layout.addWidget(self.save_button)

        self.setLayout(layout)

    def importFLAC(self):
        filepath, _ = QFileDialog.getOpenFileName(self, 'Import FLAC File', '', 'FLAC Files (*.flac)')
        if filepath:
            self.metadata = FLAC(filepath).tags
            self.populateTable()

    def saveFLAC(self):
        # Here you should implement a function to save the edited metadata
        pass

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


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = FLACTagEditor()
    window.show()
    sys.exit(app.exec_())
