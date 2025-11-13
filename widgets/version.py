from PySide6.QtWidgets import QTextEdit, QVBoxLayout
from PySide6.QtCore import Qt
import os
import re

def create_widget(BaseClass, module_name):
    class ChangelogWidget(BaseClass):
        def __init__(self):
            super().__init__(module_name)

            # layout
            layout = QVBoxLayout(self)
            self.setLayout(layout)

            self.setMinimumSize(333, 200)

            # text edit
            self.text = QTextEdit()
            self.text.setReadOnly(True)
            self.text.setStyleSheet("font-family: 'Consolas'; font-size: 8pt;")
            layout.addWidget(self.text)

            # načítanie changelogu
            self.load_changelog()

        def load_changelog(self):
            version_file = self.get_data_path("version.txt")
            changelog_text = ""
            if os.path.exists(version_file):
                with open(version_file, "r", encoding="utf-8") as f:
                    changelog_text = f.read()
            else:
                changelog_text = "[No version.txt found]"

            # konverzia na HTML
            html_lines = []
            for line in changelog_text.splitlines():
                if re.match(r"\[", line.strip()):
                    html_lines.append(f"<b>{line.strip()}</b>")
                elif line.strip() == "":
                    html_lines.append("<br>")
                else:
                    html_lines.append(f"&emsp;• {line.strip()}")

            html_content = "<br>".join(html_lines)
            self.text.setHtml(html_content)

        def close_widget(self):
            self.text.clear()

    return ChangelogWidget()

# Predvolená pozícia dock widgetu
def get_widget_dock_position():
    return Qt.RightDockWidgetArea, 1  # oblasť, poradie
