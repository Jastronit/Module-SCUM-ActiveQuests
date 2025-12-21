from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget, QLabel
from PySide6.QtCore import Qt
import os
import sys
import subprocess

def create_widget(BaseClass, module_name):
    class SettingsWidget(BaseClass):
        def __init__(self):
            super().__init__(module_name)
            main_layout = QVBoxLayout(self)
            self.setLayout(main_layout)
            self.setMaximumSize(800, 400)
            
            # Horizontálne rozloženie pre dva stĺpce
            columns_layout = QHBoxLayout()
            main_layout.addLayout(columns_layout)
            
            # ===== ĽAVÝ STĹPEC - CONFIG =====
            config_layout = QVBoxLayout()
            columns_layout.addLayout(config_layout)
            
            # Nadpis pre config
            config_label = QLabel("Configuration Files:")
            config_label.setStyleSheet("font-weight: bold;")
            config_layout.addWidget(config_label)
            
            # Zoznam config súborov
            self.config_list = QListWidget()
            self.config_list.itemDoubleClicked.connect(lambda item: self.open_file(item.text(), "config"))
            config_layout.addWidget(self.config_list)
            
            # Tlačidlo na otvorenie config súboru
            self.btn_open_config = QPushButton("Open Config File")
            self.btn_open_config.clicked.connect(lambda: self.open_selected_file("config"))
            config_layout.addWidget(self.btn_open_config)
            
            # ===== PRAVÝ STĹPEC - DATA =====
            data_layout = QVBoxLayout()
            columns_layout.addLayout(data_layout)
            
            # Nadpis pre data
            data_label = QLabel("Data Files:")
            data_label.setStyleSheet("font-weight: bold;")
            data_layout.addWidget(data_label)
            
            # Zoznam data súborov
            self.data_list = QListWidget()
            self.data_list.itemDoubleClicked.connect(lambda item: self.open_file(item.text(), "data"))
            data_layout.addWidget(self.data_list)
            
            # Tlačidlo na otvorenie data súboru
            self.btn_open_data = QPushButton("Open Data File")
            self.btn_open_data.clicked.connect(lambda: self.open_selected_file("data"))
            data_layout.addWidget(self.btn_open_data)
            
            # Načítaj súbory
            self.load_files()
        
        def get_data_path(self, filename=""):
            """Získa cestu k data zložke (rovnaká úroveň ako config)"""
            # Získaj config cestu
            config_path = self.get_config_path("")
            # Odstráň 'config' z konca a pridaj 'data'
            parent_dir = os.path.dirname(config_path.rstrip('/\\'))
            data_dir = os.path.join(parent_dir, "data")
            if filename:
                return os.path.join(data_dir, filename)
            return data_dir
        
        def load_files(self):
            """Načíta všetky súbory z config a data zložiek"""
            self.load_directory_files("config", self.config_list)
            self.load_directory_files("data", self.data_list)
        
        def load_directory_files(self, dir_name, list_widget):
            """Načíta súbory z danej zložky do daného list widgetu"""
            list_widget.clear()
            
            # Získaj cestu k zložke
            if dir_name == "config":
                dir_path = self.get_config_path("")
            else:  # data
                dir_path = self.get_data_path("")
            
            if not os.path.exists(dir_path):
                print(f"Directory does not exist: {dir_path}")
                return
            
            try:
                # Získaj všetky súbory v zložke
                files = []
                for item in os.listdir(dir_path):
                    item_path = os.path.join(dir_path, item)
                    if os.path.isfile(item_path):
                        files.append(item)
                
                # Zoraď súbory
                files.sort()
                
                # Pridaj do zoznamu
                for file in files:
                    list_widget.addItem(file)
                    
            except Exception as e:
                print(f"Error loading files from {dir_name}: {e}")
        
        def open_selected_file(self, dir_type):
            """Otvorí aktuálne vybraný súbor z daného zoznamu"""
            if dir_type == "config":
                current_item = self.config_list.currentItem()
            else:  # data
                current_item = self.data_list.currentItem()
            
            if current_item:
                filename = current_item.text()
                self.open_file(filename, dir_type)
        
        def open_file(self, filename, dir_type):
            """Otvorí súbor z danej zložky v predvolenom editore"""
            if dir_type == "config":
                file_path = self.get_config_path(filename)
            else:  # data
                file_path = self.get_data_path(filename)
            
            if not os.path.exists(file_path):
                print(f"File does not exist: {file_path}")
                return
            
            try:
                if sys.platform.startswith("win"):
                    os.startfile(file_path)
                elif sys.platform.startswith("darwin"):
                    subprocess.run(["open", file_path])
                else:
                    subprocess.run(["xdg-open", file_path])
            except Exception as e:
                print(f"Error opening file {file_path}: {e}")
    
    return SettingsWidget()

def get_widget_dock_position():
    """Predvolená pozícia dock widgetu"""
    return Qt.RightDockWidgetArea, 2  # oblasť, poradie
