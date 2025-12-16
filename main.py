import wx
import sys
import os
import subprocess
from collections import OrderedDict

from libtorrent_env import prepare_libtorrent_dlls

prepare_libtorrent_dlls()

import wx.adv
import threading
import json
import requests # Added for downloading torrent files from URL
import concurrent.futures

from clients import RTorrentClient, QBittorrentClient, TransmissionClient, LocalClient
from config_manager import ConfigManager
from session_manager import SessionManager
from torrent_creator import CreateTorrentDialog, create_torrent_bytes


# Constants for List Columns
COL_NAME = 0
COL_SIZE = 1
COL_DONE = 2
COL_UP = 3
COL_RATIO = 4
COL_STATUS = 5
APP_NAME = "SerrebiTorrent"


def get_app_icon():
    """Return a wx.Icon for the tray and main window, with a safe fallback."""
    base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    icon_path = os.path.join(base_dir, "icon.ico")

    if os.path.exists(icon_path):
        try:
            return wx.Icon(icon_path, wx.BITMAP_TYPE_ICO)
        except Exception:
            pass

    bmp = wx.ArtProvider.GetBitmap(wx.ART_INFORMATION, wx.ART_OTHER, (16, 16))
    if not bmp.IsOk():
        bmp = wx.Bitmap(16, 16)
        dc = wx.MemoryDC(bmp)
        dc.SetBackground(wx.Brush(wx.Colour(0, 0, 0)))
        dc.Clear()
        dc.SelectObject(wx.NullBitmap)

    fallback_icon = wx.Icon()
    fallback_icon.CopyFromBitmap(bmp)
    return fallback_icon

try:
    import libtorrent as lt
except ImportError:
    lt = None

class AddTorrentDialog(wx.Dialog):
    def __init__(self, parent, name, file_list=None, default_path=""):
        super().__init__(parent, title=f"Add Torrent: {name}", size=(600, 500))
        
        self.file_list = file_list or []
        self.item_map = {} # item_id -> {'name': str, 'size': int, 'idx': int or None}
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Save Path
        path_sizer = wx.BoxSizer(wx.HORIZONTAL)
        path_sizer.Add(wx.StaticText(self, label="Save Path:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.path_input = wx.TextCtrl(self, value=default_path)
        path_sizer.Add(self.path_input, 1, wx.EXPAND | wx.RIGHT, 5)
        browse_btn = wx.Button(self, label="Browse...")
        browse_btn.Bind(wx.EVT_BUTTON, self.on_browse)
        path_sizer.Add(browse_btn, 0)
        sizer.Add(path_sizer, 0, wx.EXPAND | wx.ALL, 10)
        
        # Files Tree
        if self.file_list:
            sizer.Add(wx.StaticText(self, label="Files:"), 0, wx.LEFT | wx.RIGHT, 10)
            
            # Standard TreeCtrl with text-based checkboxes
            self.tree = wx.TreeCtrl(self, style=wx.TR_DEFAULT_STYLE | wx.TR_HIDE_ROOT | wx.TR_HAS_BUTTONS | wx.TR_LINES_AT_ROOT)
            self.root = self.tree.AddRoot(name)
            self.item_map[self.root] = {'name': name, 'size': 0, 'idx': None}
            
            self.tree.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self.on_toggle)
            self.tree.Bind(wx.EVT_KEY_DOWN, self.on_key_down)
            self.tree.Bind(wx.EVT_LEFT_DOWN, self.on_click) 
            self.tree.Bind(wx.EVT_TREE_ITEM_RIGHT_CLICK, self.on_tree_context_menu)

            # Helper to find or create child
            def get_or_create_child(parent_item, text):
                (child, cookie) = self.tree.GetFirstChild(parent_item)
                while child.IsOk():
                    if self.item_map[child]['name'] == text:
                        return child
                    (child, cookie) = self.tree.GetNextChild(parent_item, cookie)
                
                item = self.tree.AppendItem(parent_item, "")
                self.item_map[item] = {'name': text, 'size': 0, 'idx': None}
                self.update_item_label(item, True) # Default checked
                return item

            for idx, (fpath, fsize) in enumerate(self.file_list):
                # Normalize path
                parts = fpath.replace('\\', '/').split('/')
                current_item = self.root
                
                for i, part in enumerate(parts):
                    if i == len(parts) - 1:
                        # Leaf
                        item = self.tree.AppendItem(current_item, "")
                        self.item_map[item] = {'name': part, 'size': fsize, 'idx': idx}
                        self.update_item_label(item, True)
                    else:
                        # Folder
                        current_item = get_or_create_child(current_item, part)
            
            self.tree.ExpandAll()
            
            sizer.Add(self.tree, 1, wx.EXPAND | wx.ALL, 10)
            
            # Select/Deselect Buttons
            btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
            sel_all = wx.Button(self, label="Select All")
            sel_all.Bind(wx.EVT_BUTTON, lambda e: self.set_root_state(True))
            btn_sizer.Add(sel_all, 0, wx.RIGHT, 5)
            
            desel_all = wx.Button(self, label="Deselect All")
            desel_all.Bind(wx.EVT_BUTTON, lambda e: self.set_root_state(False))
            btn_sizer.Add(desel_all, 0)
            
            sizer.Add(btn_sizer, 0, wx.ALIGN_LEFT | wx.LEFT | wx.BOTTOM, 10)
        else:
            sizer.Add(wx.StaticText(self, label="File list not available (Magnet link)."), 0, wx.ALL, 20)
        
        # Dialog Buttons
        btns = wx.StdDialogButtonSizer()
        btns.AddButton(wx.Button(self, wx.ID_OK))
        btns.AddButton(wx.Button(self, wx.ID_CANCEL))
        btns.Realize()
        sizer.Add(btns, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        
        self.SetSizer(sizer)
        self.Center()

    def on_browse(self, event):
        dlg = wx.DirDialog(self, "Choose Download Directory", self.path_input.GetValue())
        if dlg.ShowModal() == wx.ID_OK:
            self.path_input.SetValue(dlg.GetPath())
        dlg.Destroy()

    def fmt_size(self, size):
        if size == 0: return ""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"

    def update_item_label(self, item, checked):
        data = self.item_map.get(item)
        if not data: return
        
        prefix = "[x]" if checked else "[ ]"
        size_str = f" ({self.fmt_size(data['size'])})" if data['size'] > 0 else ""
        
        label = f"{prefix} {data['name']}{size_str}"
        self.tree.SetItemText(item, label)

    def is_checked(self, item):
        txt = self.tree.GetItemText(item)
        return txt.startswith("[x]")

    def on_toggle(self, event):
        item = event.GetItem()
        if item.IsOk():
            self.toggle_item(item)

    def on_key_down(self, event):
        code = event.GetKeyCode()
        if code == wx.WXK_SPACE:
            item = self.tree.GetSelection()
            if item.IsOk():
                self.toggle_item(item)
        else:
            event.Skip()
            
    def on_click(self, event):
        event.Skip()

    def on_tree_context_menu(self, event):
        item = event.GetItem()
        if not item.IsOk():
            item = self.tree.GetSelection()
        
        if not item.IsOk(): return

        menu = wx.Menu()
        check_item = menu.Append(wx.ID_ANY, "Check")
        uncheck_item = menu.Append(wx.ID_ANY, "Uncheck")
        menu.AppendSeparator()
        check_all = menu.Append(wx.ID_ANY, "Check All")
        uncheck_all = menu.Append(wx.ID_ANY, "Uncheck All")

        self.Bind(wx.EVT_MENU, lambda e: self.set_item_state_recursive(item, True), check_item)
        self.Bind(wx.EVT_MENU, lambda e: self.set_item_state_recursive(item, False), uncheck_item)
        self.Bind(wx.EVT_MENU, lambda e: self.set_root_state(True), check_all)
        self.Bind(wx.EVT_MENU, lambda e: self.set_root_state(False), uncheck_all)

        self.PopupMenu(menu)
        menu.Destroy()

    def toggle_item(self, item):
        new_state = not self.is_checked(item)
        self.set_item_state_recursive(item, new_state)

    def set_item_state_recursive(self, item, state):
        self.update_item_label(item, state)
        self.update_children(item, state)
        
        # Update parent up the chain
        parent = self.tree.GetItemParent(item)
        while parent.IsOk() and parent != self.root:
            self.update_parent(parent)
            parent = self.tree.GetItemParent(parent)

    def update_children(self, parent, state):
        (child, cookie) = self.tree.GetFirstChild(parent)
        while child.IsOk():
            self.update_item_label(child, state)
            self.update_children(child, state)
            (child, cookie) = self.tree.GetNextChild(parent, cookie)

    def update_parent(self, parent):
        has_checked = False
        (child, cookie) = self.tree.GetFirstChild(parent)
        while child.IsOk():
            if self.is_checked(child):
                has_checked = True
                break
            (child, cookie) = self.tree.GetNextChild(parent, cookie)
        self.update_item_label(parent, has_checked)

    def set_root_state(self, state):
        (child, cookie) = self.tree.GetFirstChild(self.root)
        while child.IsOk():
            self.set_item_state_recursive(child, state)
            (child, cookie) = self.tree.GetNextChild(self.root, cookie)

    def get_selected_path(self):
        return self.path_input.GetValue()

    def get_file_priorities(self):
        if not self.file_list:
            return None
        priorities = [0] * len(self.file_list)
        
        def traverse(item):
            if not item.IsOk(): return
            
            data = self.item_map.get(item)
            if data and data['idx'] is not None:
                priorities[data['idx']] = 1 if self.is_checked(item) else 0
                
            (child, cookie) = self.tree.GetFirstChild(item)
            while child.IsOk():
                traverse(child)
                (child, cookie) = self.tree.GetNextChild(item, cookie)

        traverse(self.root)
        return priorities


def register_associations():
    """Registers file associations for .torrent and magnet: links on Windows."""
    if sys.platform != 'win32':
        wx.MessageBox("Association is only supported on Windows for now.", "Info")
        return

    try:
        import winreg
        
        exe_path = sys.executable
        if not getattr(sys, 'frozen', False):
            python_exe = sys.executable.replace("python.exe", "pythonw.exe")
            cmd = f'"{python_exe}" "{os.path.abspath(__file__)}" "%1"'
        else:
            cmd = f'"{exe_path}" "%1"'

        # 1. Associate .torrent
        key_path = r"Software\Classes\.torrent"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.SetValue(key, "", winreg.REG_SZ, "SerrebiTorrent.Torrent")

        key_path = r"Software\Classes\SerrebiTorrent.Torrent"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.SetValue(key, "", winreg.REG_SZ, "Torrent File")
            with winreg.CreateKey(key, r"shell\open\command") as cmd_key:
                winreg.SetValue(cmd_key, "", winreg.REG_SZ, cmd)
                
        # 2. Associate magnet:
        key_path = r"Software\Classes\magnet"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.SetValue(key, "", winreg.REG_SZ, "URL:Magnet Link")
            winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
            with winreg.CreateKey(key, r"shell\open\command") as cmd_key:
                winreg.SetValue(cmd_key, "", winreg.REG_SZ, cmd)

        wx.MessageBox("Associations registered successfully!", "Success")
    except Exception as e:
        wx.LogError(f"Failed to register associations: {e}")

class TorrentListCtrl(wx.ListCtrl):
    def __init__(self, parent, id=wx.ID_ANY, pos=wx.DefaultPosition,
                 size=wx.DefaultSize, style=wx.LC_REPORT | wx.LC_VIRTUAL | wx.LC_HRULES | wx.LC_VRULES):
        super().__init__(parent, id, pos, size, style)
        
        self.data = [] # List of lists of strings

        self.InsertColumn(COL_NAME, "Name", width=300)
        self.InsertColumn(COL_SIZE, "Size", width=100)
        self.InsertColumn(COL_DONE, "Done", width=100)
        self.InsertColumn(COL_UP, "Uploaded", width=100)
        self.InsertColumn(COL_RATIO, "Ratio", width=80)
        self.InsertColumn(COL_STATUS, "Status", width=200)

        self.SetName("Torrent List")

    def OnGetItemText(self, item, col):
        if item >= len(self.data):
            return ""
        try:
            return self.data[item][col]
        except IndexError:
            return ""

    def update_data(self, new_data):
        self.data = new_data
        current_count = self.GetItemCount()
        new_count = len(self.data)
        
        if current_count != new_count:
            self.SetItemCount(new_count)
        
        if new_count > 0:
            self.Refresh()

    def get_selected_hashes(self):
        count = self.GetSelectedItemCount()
        selection = []
        item = self.GetFirstSelected()
        while item != -1:
            try:
                selection.append(self.data[item][6]) 
            except:
                pass
            item = self.GetNextSelected(item)
        return selection

class ProfileDialog(wx.Dialog):
    def __init__(self, parent, profile=None):
        title = "Edit Profile" if profile else "Add Profile"
        super().__init__(parent, title=title)
        
        self.profile = profile
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Name
        sizer.Add(wx.StaticText(self, label="Profile Name:"), 0, wx.ALL, 5)
        self.name_input = wx.TextCtrl(self, value=profile['name'] if profile else "")
        sizer.Add(self.name_input, 0, wx.EXPAND | wx.ALL, 5)
        
        # Type
        sizer.Add(wx.StaticText(self, label="Client Type:"), 0, wx.ALL, 5)
        self.type_input = wx.Choice(self, choices=["local", "rtorrent", "qbittorrent", "transmission"])
        self.type_input.Bind(wx.EVT_CHOICE, self.on_type_change)
        if profile:
            self.type_input.SetStringSelection(profile.get('type', 'local'))
        else:
            self.type_input.SetSelection(0)
        sizer.Add(self.type_input, 0, wx.EXPAND | wx.ALL, 5)
        
        # URL / Path (or local download path)
        self.url_label = wx.StaticText(self, label="URL (e.g. scgi://... or http://...):")
        sizer.Add(self.url_label, 0, wx.ALL, 5)

        url_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.url_input = wx.TextCtrl(self, value=profile['url'] if profile else "")
        url_sizer.Add(self.url_input, 1, wx.EXPAND | wx.RIGHT, 5)

        self.url_browse_btn = wx.Button(self, label="Browse...")
        self.url_browse_btn.Bind(wx.EVT_BUTTON, self.on_browse_url_path)
        url_sizer.Add(self.url_browse_btn, 0)

        sizer.Add(url_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        # User
        self.user_label = wx.StaticText(self, label="Username:")
        sizer.Add(self.user_label, 0, wx.ALL, 5)
        self.user_input = wx.TextCtrl(self, value=profile['user'] if profile else "")
        sizer.Add(self.user_input, 0, wx.EXPAND | wx.ALL, 5)
        
        # Pass
        self.pass_label = wx.StaticText(self, label="Password:")
        sizer.Add(self.pass_label, 0, wx.ALL, 5)
        self.pass_input = wx.TextCtrl(self, value=profile['password'] if profile else "", style=wx.TE_PASSWORD)
        sizer.Add(self.pass_input, 0, wx.EXPAND | wx.ALL, 5)
        
        btns = wx.StdDialogButtonSizer()
        btns.AddButton(wx.Button(self, wx.ID_OK))
        btns.AddButton(wx.Button(self, wx.ID_CANCEL))
        btns.Realize()
        sizer.Add(btns, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        
        self.SetSizer(sizer)
        self.Fit()
        self.Center()
        
        # Trigger initial update
        self.on_type_change(None)

    def on_type_change(self, event):
        sel = self.type_input.GetStringSelection()
        if sel == "local":
            self.url_label.SetLabel("Download Path:")
            if hasattr(self, 'url_browse_btn'):
                self.url_browse_btn.Show(True)
            self.user_input.Disable()
            self.pass_input.Disable()
        else:
            self.url_label.SetLabel("URL (e.g. scgi://... or http://...):")
            if hasattr(self, 'url_browse_btn'):
                self.url_browse_btn.Show(False)
            self.user_input.Enable()
            self.pass_input.Enable()

        self.Layout()


    def on_browse_url_path(self, event):
        # Used when profile type is 'local' to choose a download folder.
        start = self.url_input.GetValue().strip()
        if not start or not os.path.isdir(start):
            start = os.path.expanduser("~")
        dlg = wx.DirDialog(self, "Choose Download Folder", start, style=wx.DD_DEFAULT_STYLE)
        if dlg.ShowModal() == wx.ID_OK:
            self.url_input.SetValue(dlg.GetPath())
        dlg.Destroy()

    def GetProfileData(self):
        return {
            "name": self.name_input.GetValue(),
            "type": self.type_input.GetStringSelection(),
            "url": self.url_input.GetValue(),
            "user": self.user_input.GetValue(),
            "password": self.pass_input.GetValue()
        }

class ConnectDialog(wx.Dialog):
    def __init__(self, parent, config_manager):
        super().__init__(parent, title="Connection Manager", size=(500, 300))
        self.cm = config_manager
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # List of Profiles
        self.list_box = wx.ListBox(self, style=wx.LB_SINGLE)
        sizer.Add(self.list_box, 1, wx.EXPAND | wx.ALL, 10)
        
        # Buttons Row
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        add_btn = wx.Button(self, label="Add")
        add_btn.Bind(wx.EVT_BUTTON, self.on_add)
        btn_sizer.Add(add_btn, 0, wx.RIGHT, 5)
        
        edit_btn = wx.Button(self, label="Edit")
        edit_btn.Bind(wx.EVT_BUTTON, self.on_edit)
        btn_sizer.Add(edit_btn, 0, wx.RIGHT, 5)
        
        del_btn = wx.Button(self, label="Delete")
        del_btn.Bind(wx.EVT_BUTTON, self.on_delete)
        btn_sizer.Add(del_btn, 0, wx.RIGHT, 5)
        
        set_def_btn = wx.Button(self, label="Set Default")
        set_def_btn.Bind(wx.EVT_BUTTON, self.on_set_default)
        btn_sizer.Add(set_def_btn, 0, wx.RIGHT, 5)
        
        connect_btn = wx.Button(self, label="Connect")
        connect_btn.Bind(wx.EVT_BUTTON, self.on_connect)
        btn_sizer.Add(connect_btn, 0, wx.LEFT, 20)
        
        close_btn = wx.Button(self, wx.ID_CANCEL, label="Close")
        close_btn.Bind(wx.EVT_BUTTON, lambda evt: self.EndModal(wx.ID_CANCEL))
        btn_sizer.Add(close_btn, 0, wx.LEFT, 10)
        
        sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        
        self.SetSizer(sizer)
        self.Center()

        try:
            self.SetEscapeId(wx.ID_CANCEL)
        except Exception:
            pass

        self.Bind(wx.EVT_CHAR_HOOK, self.on_char_hook)
        
        self.selected_profile_id = None
        self.refresh_list()

    
    def on_char_hook(self, event):
        try:
            key = event.GetKeyCode()
        except Exception:
            key = None

        if key == wx.WXK_ESCAPE:
            try:
                self.EndModal(wx.ID_CANCEL)
            except Exception:
                try:
                    self.Close()
                except Exception:
                    pass
            return

        try:
            event.Skip()
        except Exception:
            pass

    def refresh_list(self):
        self.list_box.Clear()
        self.profiles_map = [] # Index -> ID
        
        profiles = self.cm.get_profiles()
        default_id = self.cm.get_default_profile_id()
        
        for pid, p in profiles.items():
            label = p['name']
            if pid == default_id:
                label += " (Default)"
            self.list_box.Append(label)
            self.profiles_map.append(pid)
            
        # Select first if any
        if self.profiles_map:
            self.list_box.SetSelection(0)

    def get_selected_id(self):
        sel = self.list_box.GetSelection()
        if sel != wx.NOT_FOUND:
            return self.profiles_map[sel]
        return None

    def on_add(self, event):
        dlg = ProfileDialog(self)
        if dlg.ShowModal() == wx.ID_OK:
            data = dlg.GetProfileData()
            self.cm.add_profile(data['name'], data['type'], data['url'], data['user'], data['password'])
            self.refresh_list()
        dlg.Destroy()

    def on_edit(self, event):
        pid = self.get_selected_id()
        if not pid: return
        
        p = self.cm.get_profile(pid)
        dlg = ProfileDialog(self, p)
        if dlg.ShowModal() == wx.ID_OK:
            data = dlg.GetProfileData()
            self.cm.update_profile(pid, data['name'], data['type'], data['url'], data['user'], data['password'])
            self.refresh_list()
        dlg.Destroy()

    def on_delete(self, event):
        pid = self.get_selected_id()
        if pid and wx.MessageBox("Delete this profile?", "Confirm", wx.YES_NO) == wx.YES:
            self.cm.delete_profile(pid)
            self.refresh_list()

    def on_set_default(self, event):
        pid = self.get_selected_id()
        if pid:
            self.cm.set_default_profile_id(pid)
            self.refresh_list()

    def on_connect(self, event):
        self.selected_profile_id = self.get_selected_id()
        if self.selected_profile_id:
            self.EndModal(wx.ID_OK)
        else:
            wx.MessageBox("Please select a profile to connect.", "Warning")


class PreferencesDialog(wx.Dialog):
    def __init__(self, parent, config_manager):
        super().__init__(parent, title="Preferences", size=(500, 500))
        self.cm = config_manager
        self.prefs = self.cm.get_preferences()
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        notebook = wx.Notebook(self)
        
        # --- General Tab ---
        general_panel = wx.Panel(notebook)
        gen_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Download Path
        gen_sizer.Add(wx.StaticText(general_panel, label="Default Download Path:"), 0, wx.ALL, 5)
        path_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.path_input = wx.TextCtrl(general_panel, value=self.prefs.get('download_path', ''))
        path_sizer.Add(self.path_input, 1, wx.EXPAND | wx.RIGHT, 5)
        browse_btn = wx.Button(general_panel, label="Browse...")
        browse_btn.Bind(wx.EVT_BUTTON, self.on_browse)
        path_sizer.Add(browse_btn, 0)
        gen_sizer.Add(path_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        # Behavior
        self.auto_start_chk = wx.CheckBox(general_panel, label="Automatically start torrents")
        self.auto_start_chk.SetValue(self.prefs.get('auto_start', True))
        gen_sizer.Add(self.auto_start_chk, 0, wx.ALL, 5)
        
        self.min_tray_chk = wx.CheckBox(general_panel, label="Minimize to System Tray")
        self.min_tray_chk.SetValue(self.prefs.get('min_to_tray', True))
        gen_sizer.Add(self.min_tray_chk, 0, wx.ALL, 5)
        
        self.close_tray_chk = wx.CheckBox(general_panel, label="Close to System Tray")
        self.close_tray_chk.SetValue(self.prefs.get('close_to_tray', True))
        gen_sizer.Add(self.close_tray_chk, 0, wx.ALL, 5)
        
        general_panel.SetSizer(gen_sizer)
        notebook.AddPage(general_panel, "General")
        
        # --- Connection Tab ---
        conn_panel = wx.Panel(notebook)
        conn_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Limits
        conn_sizer.Add(wx.StaticText(conn_panel, label="Global Limits (0 or -1 for unlimited):"), 0, wx.ALL, 5)
        
        grid = wx.FlexGridSizer(4, 2, 10, 10)
        
        grid.Add(wx.StaticText(conn_panel, label="Download Rate (bytes/s):"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.dl_limit = wx.SpinCtrl(conn_panel, min=-1, max=1000000000, initial=self.prefs.get('dl_limit', 0))
        grid.Add(self.dl_limit, 0, wx.EXPAND)
        
        grid.Add(wx.StaticText(conn_panel, label="Upload Rate (bytes/s):"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.ul_limit = wx.SpinCtrl(conn_panel, min=-1, max=1000000000, initial=self.prefs.get('ul_limit', 0))
        grid.Add(self.ul_limit, 0, wx.EXPAND)
        
        grid.Add(wx.StaticText(conn_panel, label="Max Connections:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.max_conn = wx.SpinCtrl(conn_panel, min=-1, max=65535, initial=self.prefs.get('max_connections', -1))
        grid.Add(self.max_conn, 0, wx.EXPAND)
        
        grid.Add(wx.StaticText(conn_panel, label="Max Upload Slots:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.max_slots = wx.SpinCtrl(conn_panel, min=-1, max=65535, initial=self.prefs.get('max_uploads', -1))
        grid.Add(self.max_slots, 0, wx.EXPAND)
        
        conn_sizer.Add(grid, 0, wx.ALL, 10)
        
        # Network
        conn_sizer.Add(wx.StaticLine(conn_panel), 0, wx.EXPAND | wx.ALL, 5)
        
        port_sizer = wx.BoxSizer(wx.HORIZONTAL)
        port_sizer.Add(wx.StaticText(conn_panel, label="Listening Port:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.port_input = wx.SpinCtrl(conn_panel, min=1, max=65535, initial=self.prefs.get('listen_port', 6881))
        port_sizer.Add(self.port_input, 0)
        conn_sizer.Add(port_sizer, 0, wx.ALL, 10)
        
        self.upnp_chk = wx.CheckBox(conn_panel, label="Enable UPnP Port Mapping")
        self.upnp_chk.SetValue(self.prefs.get('enable_upnp', True))
        conn_sizer.Add(self.upnp_chk, 0, wx.ALL, 5)
        
        self.natpmp_chk = wx.CheckBox(conn_panel, label="Enable NAT-PMP Port Mapping")
        self.natpmp_chk.SetValue(self.prefs.get('enable_natpmp', True))
        conn_sizer.Add(self.natpmp_chk, 0, wx.ALL, 5)

        self.dht_chk = wx.CheckBox(conn_panel, label="Enable DHT")
        self.dht_chk.SetValue(self.prefs.get('enable_dht', True))
        conn_sizer.Add(self.dht_chk, 0, wx.ALL, 5)

        self.lsd_chk = wx.CheckBox(conn_panel, label="Enable Local Service Discovery (LSD)")
        self.lsd_chk.SetValue(self.prefs.get('enable_lsd', True))
        conn_sizer.Add(self.lsd_chk, 0, wx.ALL, 5)
        
        conn_panel.SetSizer(conn_sizer)
        notebook.AddPage(conn_panel, "Connection")
        
        # --- Trackers Tab ---
        track_panel = wx.Panel(notebook)
        track_sizer = wx.BoxSizer(wx.VERTICAL)
        
        self.track_chk = wx.CheckBox(track_panel, label="Automatically add trackers from URL")
        self.track_chk.SetValue(self.prefs.get('enable_trackers', True))
        track_sizer.Add(self.track_chk, 0, wx.ALL, 5)
        
        track_sizer.Add(wx.StaticText(track_panel, label="Tracker List URL:"), 0, wx.ALL, 5)
        self.track_url_input = wx.TextCtrl(track_panel, value=self.prefs.get('tracker_url', ''))
        track_sizer.Add(self.track_url_input, 0, wx.EXPAND | wx.ALL, 5)
        
        track_panel.SetSizer(track_sizer)
        notebook.AddPage(track_panel, "Trackers")
        
        # --- Proxy Tab ---
        proxy_panel = wx.Panel(notebook)
        proxy_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Proxy Type
        proxy_sizer.Add(wx.StaticText(proxy_panel, label="Proxy Type:"), 0, wx.ALL, 5)
        self.proxy_type = wx.Choice(proxy_panel, choices=["None", "SOCKS4", "SOCKS5", "HTTP"])
        self.proxy_type.SetSelection(self.prefs.get('proxy_type', 0))
        proxy_sizer.Add(self.proxy_type, 0, wx.EXPAND | wx.ALL, 5)
        
        # Host & Port
        hp_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        hp_sizer.Add(wx.StaticText(proxy_panel, label="Host:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.proxy_host = wx.TextCtrl(proxy_panel, value=self.prefs.get('proxy_host', ''))
        hp_sizer.Add(self.proxy_host, 1, wx.EXPAND | wx.RIGHT, 10)
        
        hp_sizer.Add(wx.StaticText(proxy_panel, label="Port:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.proxy_port = wx.SpinCtrl(proxy_panel, min=1, max=65535, initial=self.prefs.get('proxy_port', 8080))
        hp_sizer.Add(self.proxy_port, 0)
        
        proxy_sizer.Add(hp_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        # Auth
        proxy_sizer.Add(wx.StaticText(proxy_panel, label="Authentication (if required):"), 0, wx.TOP | wx.LEFT, 10)
        
        user_sizer = wx.BoxSizer(wx.HORIZONTAL)
        user_sizer.Add(wx.StaticText(proxy_panel, label="Username:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.proxy_user = wx.TextCtrl(proxy_panel, value=self.prefs.get('proxy_user', ''))
        user_sizer.Add(self.proxy_user, 1, wx.EXPAND)
        proxy_sizer.Add(user_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        pass_sizer = wx.BoxSizer(wx.HORIZONTAL)
        pass_sizer.Add(wx.StaticText(proxy_panel, label="Password:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.proxy_pass = wx.TextCtrl(proxy_panel, value=self.prefs.get('proxy_password', ''), style=wx.TE_PASSWORD)
        pass_sizer.Add(self.proxy_pass, 1, wx.EXPAND)
        proxy_sizer.Add(pass_sizer, 0, wx.EXPAND | wx.ALL, 5)

        proxy_panel.SetSizer(proxy_sizer)
        notebook.AddPage(proxy_panel, "Proxy")
        
        sizer.Add(notebook, 1, wx.EXPAND | wx.ALL, 5)
        
        # Buttons
        btns = wx.StdDialogButtonSizer()
        btns.AddButton(wx.Button(self, wx.ID_OK))
        btns.AddButton(wx.Button(self, wx.ID_CANCEL))
        btns.Realize()
        sizer.Add(btns, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        
        self.SetSizer(sizer)
        self.Center()

    def on_browse(self, event):
        dlg = wx.DirDialog(self, "Choose Download Directory", self.path_input.GetValue())
        if dlg.ShowModal() == wx.ID_OK:
            self.path_input.SetValue(dlg.GetPath())
        dlg.Destroy()

    def get_preferences(self):
        return {
            "download_path": self.path_input.GetValue(),
            "auto_start": self.auto_start_chk.GetValue(),
            "min_to_tray": self.min_tray_chk.GetValue(),
            "close_to_tray": self.close_tray_chk.GetValue(),
            "dl_limit": self.dl_limit.GetValue(),
            "ul_limit": self.ul_limit.GetValue(),
            "max_connections": self.max_conn.GetValue(),
            "max_uploads": self.max_slots.GetValue(),
            "listen_port": self.port_input.GetValue(),
            "enable_upnp": self.upnp_chk.GetValue(),
            "enable_natpmp": self.natpmp_chk.GetValue(),
            "enable_dht": self.dht_chk.GetValue() if hasattr(self, "dht_chk") else self.prefs.get("enable_dht", True),
            "enable_lsd": self.lsd_chk.GetValue() if hasattr(self, "lsd_chk") else self.prefs.get("enable_lsd", True),
            "enable_trackers": self.track_chk.GetValue(),
            "tracker_url": self.track_url_input.GetValue(),
            "proxy_type": self.proxy_type.GetSelection(),
            "proxy_host": self.proxy_host.GetValue(),
            "proxy_port": self.proxy_port.GetValue(),
            "proxy_user": self.proxy_user.GetValue(),
            "proxy_password": self.proxy_pass.GetValue()
        }


class RemotePreferencesDialog(wx.Dialog):
    CATEGORY_FIELDS = OrderedDict([
        ("General", [
            "locale", "create_subfolder_enabled", "start_paused_enabled", "auto_delete_mode",
            "preallocate_all", "incomplete_files_ext", "auto_tmm_enabled", "torrent_changed_tmm_enabled",
            "save_path_changed_tmm_enabled", "category_changed_tmm_enabled", "save_path",
            "temp_path_enabled", "temp_path", "scan_dirs", "export_dir", "export_dir_fin"
        ]),
        ("Downloads", [
            "autorun_enabled", "autorun_program", "queueing_enabled", "max_active_downloads",
            "max_active_torrents", "max_active_uploads", "dont_count_slow_torrents",
            "slow_torrent_dl_rate_threshold", "slow_torrent_ul_rate_threshold", "slow_torrent_inactive_timer",
            "max_ratio_enabled", "max_ratio", "max_ratio_act", "add_trackers_enabled", "add_trackers",
            "max_seeding_time_enabled", "max_seeding_time", "announce_ip", "announce_to_all_tiers",
            "announce_to_all_trackers", "recheck_completed_torrents", "resolve_peer_countries",
            "save_resume_data_interval", "send_buffer_low_watermark", "send_buffer_watermark",
            "send_buffer_watermark_factor", "socket_backlog_size"
        ]),
        ("Connection", [
            "listen_port", "upnp", "random_port", "max_connec", "max_connec_per_torrent", "max_uploads",
            "max_uploads_per_torrent", "stop_tracker_timeout", "upnp_lease_duration", "outgoing_ports_min",
            "outgoing_ports_max", "current_interface_address", "current_network_interface"
        ]),
        ("Speed", [
            "dl_limit", "up_limit", "alt_dl_limit", "alt_up_limit"
        ]),
        ("BitTorrent", [
            "dht", "pex", "lsd", "encryption", "anonymous_mode", "proxy_type", "proxy_ip",
            "proxy_port", "proxy_peer_connections", "proxy_auth_enabled", "proxy_username",
            "proxy_password", "proxy_torrents_only", "bittorrent_protocol", "enable_piece_extent_affinity",
            "limit_utp_rate", "limit_tcp_overhead", "limit_lan_peers", "async_io_threads", "banned_IPs",
            "checking_memory_use", "disk_cache", "disk_cache_ttl", "embedded_tracker_port",
            "enable_coalesce_read_write", "enable_embedded_tracker", "enable_multi_connections_from_same_ip",
            "enable_os_cache", "enable_upload_suggestions", "file_pool_size", "upload_choking_algorithm",
            "upload_slots_behavior", "utp_tcp_mixed_mode"
        ]),
        ("Scheduler", [
            "scheduler_enabled", "schedule_from_hour", "schedule_from_min", "schedule_to_hour",
            "schedule_to_min", "scheduler_days"
        ]),
        ("Web UI", [
            "web_ui_domain_list", "web_ui_address", "web_ui_port", "web_ui_upnp", "web_ui_username",
            "web_ui_password", "web_ui_csrf_protection_enabled", "web_ui_clickjacking_protection_enabled",
            "web_ui_secure_cookie_enabled", "web_ui_max_auth_fail_count", "web_ui_ban_duration",
            "web_ui_session_timeout", "web_ui_host_header_validation_enabled", "bypass_local_auth",
            "bypass_auth_subnet_whitelist_enabled", "bypass_auth_subnet_whitelist",
            "alternative_webui_enabled", "alternative_webui_path", "use_https", "ssl_key", "ssl_cert",
            "web_ui_https_key_path", "web_ui_https_cert_path", "dyndns_enabled", "dyndns_service",
            "dyndns_username", "dyndns_password", "dyndns_domain", "web_ui_use_custom_http_headers_enabled",
            "web_ui_custom_http_headers"
        ]),
        ("Notifications", [
            "mail_notification_enabled", "mail_notification_sender", "mail_notification_email",
            "mail_notification_smtp", "mail_notification_ssl_enabled", "mail_notification_auth_enabled",
            "mail_notification_username", "mail_notification_password", "rss_refresh_interval",
            "rss_max_articles_per_feed", "rss_processing_enabled", "rss_auto_downloading_enabled",
            "rss_download_repack_proper_episodes", "rss_smart_episode_filters"
        ])
    ])

    BOOL_KEYS = {
        "create_subfolder_enabled", "start_paused_enabled", "preallocate_all", "incomplete_files_ext",
        "auto_tmm_enabled", "torrent_changed_tmm_enabled", "save_path_changed_tmm_enabled",
        "category_changed_tmm_enabled", "temp_path_enabled", "mail_notification_enabled",
        "mail_notification_ssl_enabled", "mail_notification_auth_enabled", "autorun_enabled",
        "queueing_enabled", "dont_count_slow_torrents", "max_ratio_enabled", "upnp", "random_port",
        "limit_utp_rate", "limit_tcp_overhead", "limit_lan_peers", "scheduler_enabled", "dht", "pex",
        "lsd", "anonymous_mode", "proxy_peer_connections", "proxy_auth_enabled", "proxy_torrents_only",
        "ip_filter_enabled", "ip_filter_trackers", "web_ui_upnp", "web_ui_csrf_protection_enabled",
        "web_ui_clickjacking_protection_enabled", "web_ui_secure_cookie_enabled",
        "web_ui_host_header_validation_enabled", "bypass_local_auth",
        "bypass_auth_subnet_whitelist_enabled", "alternative_webui_enabled", "use_https",
        "dyndns_enabled", "rss_processing_enabled", "rss_auto_downloading_enabled",
        "rss_download_repack_proper_episodes", "add_trackers_enabled",
        "web_ui_use_custom_http_headers_enabled", "max_seeding_time_enabled",
        "announce_to_all_tiers", "announce_to_all_trackers", "enable_piece_extent_affinity",
        "enable_coalesce_read_write", "enable_embedded_tracker",
        "enable_multi_connections_from_same_ip", "enable_os_cache", "enable_upload_suggestions",
        "recheck_completed_torrents", "resolve_peer_countries"
    }

    MULTILINE_FIELDS = {
        "add_trackers", "banned_IPs", "bypass_auth_subnet_whitelist",
        "web_ui_custom_http_headers", "rss_smart_episode_filters", "ssl_key", "ssl_cert"
    }

    JSON_FIELDS = {"scan_dirs"}
    PASSWORD_FIELDS = {"proxy_password", "mail_notification_password", "web_ui_password", "dyndns_password"}

    ENUM_CHOICES = {
        "scheduler_days": [
            ("Every day", 0), ("Every weekday", 1), ("Every weekend", 2), ("Every Monday", 3),
            ("Every Tuesday", 4), ("Every Wednesday", 5), ("Every Thursday", 6),
            ("Every Friday", 7), ("Every Saturday", 8), ("Every Sunday", 9)
        ],
        "encryption": [
            ("Prefer encryption", 0), ("Force encryption on", 1), ("Force encryption off", 2)
        ],
        "proxy_type": [
            ("Proxy disabled", -1), ("HTTP (no auth)", 1), ("SOCKS5 (no auth)", 2),
            ("HTTP (with auth)", 3), ("SOCKS5 (with auth)", 4), ("SOCKS4 (no auth)", 5)
        ],
        "dyndns_service": [
            ("Use DyDNS", 0), ("Use NOIP", 1)
        ],
        "max_ratio_act": [
            ("Pause torrent", 0), ("Remove torrent", 1)
        ],
        "bittorrent_protocol": [
            ("TCP and uTP", 0), ("TCP", 1), ("uTP", 2)
        ],
        "upload_choking_algorithm": [
            ("Round-robin", 0), ("Fastest upload", 1), ("Anti-leech", 2)
        ],
        "upload_slots_behavior": [
            ("Fixed slots", 0), ("Upload-rate based", 1)
        ],
        "utp_tcp_mixed_mode": [
            ("Prefer TCP", 0), ("Peer proportional", 1)
        ]
    }

    def __init__(self, parent, prefs):
        super().__init__(parent, title="qBittorrent Remote Preferences", size=(900, 640))
        self.prefs = OrderedDict(prefs or {})
        self.field_controls = {}

        sizer = wx.BoxSizer(wx.VERTICAL)
        intro = wx.StaticText(
            self,
            label="Edit the remote qBittorrent application preferences. Boolean options appear as checkboxes."
        )
        sizer.Add(intro, 0, wx.ALL, 10)

        notebook = wx.Notebook(self)
        assigned = set()

        for category, keys in self.CATEGORY_FIELDS.items():
            selected_keys = [key for key in keys if key in self.prefs]
            if not selected_keys:
                continue
            panel = self._build_category_panel(notebook, category, selected_keys)
            notebook.AddPage(panel, category)
            assigned.update(selected_keys)

        remaining = [k for k in self.prefs if k not in assigned]
        if remaining:
            panel = self._build_category_panel(notebook, "Advanced", remaining)
            notebook.AddPage(panel, "Advanced")

        if notebook.GetPageCount() == 0:
            placeholder = wx.Panel(notebook)
            placeholder_sizer = wx.BoxSizer(wx.VERTICAL)
            placeholder_sizer.Add(
                wx.StaticText(placeholder, label="Remote client did not return any preferences."),
                1,
                wx.ALL | wx.EXPAND,
                10
            )
            placeholder.SetSizer(placeholder_sizer)
            notebook.AddPage(placeholder, "Preferences")

        sizer.Add(notebook, 1, wx.EXPAND | wx.ALL, 5)

        btns = wx.StdDialogButtonSizer()
        btns.AddButton(wx.Button(self, wx.ID_OK))
        btns.AddButton(wx.Button(self, wx.ID_CANCEL))
        btns.Realize()
        sizer.Add(btns, 0, wx.ALIGN_CENTER | wx.ALL, 10)

        self.SetSizer(sizer)
        self.Layout()
        self.Center()

    def _build_category_panel(self, parent, category, keys):
        panel = wx.ScrolledWindow(parent, style=wx.VSCROLL)
        panel.SetScrollRate(0, 10)
        panel.SetMinSize((840, 360))
        layout = wx.BoxSizer(wx.VERTICAL)

        for key in keys:
            field = self._create_field(panel, key)
            layout.Add(field, 0, wx.EXPAND | wx.ALL, 4)

        panel.SetSizer(layout)
        panel.Layout()
        panel.FitInside()
        return panel

    def _create_field(self, panel, key):
        value = self.prefs.get(key)
        field_type = self._determine_field_type(key, value)
        field_sizer = wx.BoxSizer(wx.HORIZONTAL)

        if field_type == "bool":
            label = self._format_label(key)
            control = wx.CheckBox(panel, label=label)
            control.SetValue(bool(value))
            field_sizer.Add(control, 1, wx.ALIGN_CENTER_VERTICAL)
        else:
            label_ctrl = wx.StaticText(panel, label=f"{self._format_label(key)}:")
            field_sizer.Add(label_ctrl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
            control = self._create_non_bool_control(panel, key, value, field_type)
            field_sizer.Add(control, 1, wx.EXPAND)

        self.field_controls[key] = {
            "control": control,
            "type": field_type,
            "choices": self.ENUM_CHOICES.get(key)
        }
        return field_sizer

    def _create_non_bool_control(self, panel, key, value, field_type):
        if field_type == "choice":
            choices = [label for label, _ in self.ENUM_CHOICES.get(key, [])]
            control = wx.Choice(panel, choices=choices)
            selection = 0
            for idx, (_, val) in enumerate(self.ENUM_CHOICES.get(key, [])):
                if val == value:
                    selection = idx
                    break
            control.SetSelection(selection)
            return control

        style = 0
        if key in self.MULTILINE_FIELDS or field_type == "json":
            style |= wx.TE_MULTILINE
        if key in self.PASSWORD_FIELDS:
            style |= wx.TE_PASSWORD

        control = wx.TextCtrl(panel, style=style | wx.TE_RICH2 if field_type == "json" else style)

        if field_type == "json":
            payload = json.dumps(value, indent=2) if value else ""
            control.SetValue(payload)
            control.SetMinSize((420, 100))
            control.SetToolTip("Enter a JSON object (e.g. {\"/watched\": \"/home/user\"}).")
            return control

        text_value = ""
        if value is not None:
            text_value = str(value)
        control.SetValue(text_value)
        control.SetMinSize((420, 24 if not (style & wx.TE_MULTILINE) else 100))
        if key in self.PASSWORD_FIELDS:
            control.SetHint("Leave blank to retain the current password.")
        return control

    def _determine_field_type(self, key, value):
        if key in self.BOOL_KEYS:
            return "bool"
        if isinstance(value, bool):
            return "bool"
        if key in self.ENUM_CHOICES:
            return "choice"
        if key in self.JSON_FIELDS or isinstance(value, (dict, list)):
            return "json"
        if isinstance(value, float):
            return "float"
        if isinstance(value, int):
            return "int"
        return "string"

    def _format_label(self, key):
        label = key.replace("_", " ").title()
        replacements = {
            "Web Ui": "Web UI",
            "Ssl": "SSL",
            "Http": "HTTP",
            "Dns": "DNS",
            "Ip": "IP",
            "Ut P": "uTP",
            "Tcp": "TCP",
            "Lng": "LNG"
        }
        for old, new in replacements.items():
            label = label.replace(old, new)
        return label

    def GetPreferences(self):
        prefs = {}
        for key, meta in self.field_controls.items():
            control = meta["control"]
            field_type = meta["type"]

            if field_type == "bool":
                prefs[key] = bool(control.GetValue())
                continue

            if field_type == "choice":
                selection = control.GetSelection()
                choices = meta.get("choices") or []
                if choices and selection >= 0:
                    prefs[key] = choices[selection][1]
                continue

            text = control.GetValue()

            if field_type == "json":
                stripped = text.strip()
                if not stripped:
                    prefs[key] = {}
                    continue
                try:
                    prefs[key] = json.loads(text)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSON for {self._format_label(key)}: {exc}")
                continue

            if field_type == "int":
                stripped = text.strip()
                if stripped == "":
                    prefs[key] = self.prefs.get(key, 0)
                    continue
                try:
                    prefs[key] = int(stripped)
                except ValueError as exc:
                    raise ValueError(f"Invalid integer for {self._format_label(key)}: {exc}")
                continue

            if field_type == "float":
                stripped = text.strip()
                if stripped == "":
                    prefs[key] = self.prefs.get(key, 0.0)
                    continue
                try:
                    prefs[key] = float(stripped)
                except ValueError as exc:
                    raise ValueError(f"Invalid number for {self._format_label(key)}: {exc}")
                continue

            if key in self.PASSWORD_FIELDS and not text:
                continue

            prefs[key] = text

        return prefs

class TaskBarIcon(wx.adv.TaskBarIcon):
    def __init__(self, frame):
        super().__init__()
        self.frame = frame
        self.SetIcon(get_app_icon(), APP_NAME)
        # Bind both double click and single click (UP) to restore.
        # This ensures Enter (often mapped to click/dblclick) and single left click open the app.
        self.Bind(wx.adv.EVT_TASKBAR_LEFT_DCLICK, self.on_restore)
        self.Bind(wx.adv.EVT_TASKBAR_LEFT_UP, self.on_restore)

    def CreatePopupMenu(self):
        menu = wx.Menu()
        restore = menu.Append(wx.ID_ANY, "Restore")
        self.Bind(wx.EVT_MENU, self.on_restore, restore)

        menu.AppendSeparator()
        start_item = menu.Append(wx.ID_ANY, "Start")
        stop_item = menu.Append(wx.ID_ANY, "Stop")
        pause_item = menu.Append(wx.ID_ANY, "Pause")
        resume_item = menu.Append(wx.ID_ANY, "Resume")
        self.Bind(wx.EVT_MENU, self.on_start, start_item)
        self.Bind(wx.EVT_MENU, self.on_pause, pause_item)
        self.Bind(wx.EVT_MENU, self.on_resume, resume_item)
        self.Bind(wx.EVT_MENU, self.on_recheck, recheck_item)
        self.Bind(wx.EVT_MENU, self.on_reannounce, reannounce_item)
        self.Bind(wx.EVT_MENU, self.on_copy_info_hash, copy_hash_item)
        self.Bind(wx.EVT_MENU, self.on_copy_magnet, copy_magnet_item)
        self.Bind(wx.EVT_MENU, self.on_open_download_folder, open_folder_item)
        self.Bind(wx.EVT_MENU, self.on_pause, pause_item)
        self.Bind(wx.EVT_MENU, self.on_resume, resume_item)

        menu.AppendSeparator()
        profile_menu = wx.Menu()
        profiles = self.frame.config_manager.get_profiles()
        if profiles:
            for pid, profile in profiles.items():
                label = profile.get("name") or pid
                item = profile_menu.Append(wx.ID_ANY, label)
                self.Bind(wx.EVT_MENU, lambda event, pid=pid: self.on_switch_profile(pid), item)
        else:
            empty = profile_menu.Append(wx.ID_ANY, "No Profiles Configured")
            empty.Enable(False)
        menu.AppendSubMenu(profile_menu, "Switch Profile")

        menu.AppendSeparator()
        exit_item = menu.Append(wx.ID_EXIT, "Exit")
        self.Bind(wx.EVT_MENU, self.on_exit, exit_item)
        return menu

    def on_double_click(self, event):
        self.on_restore(event)

    def on_restore(self, event):
        self.frame.show_from_tray()

    def on_start(self, event):
        wx.CallAfter(self.frame.on_start, None)

    def on_stop(self, event):
        wx.CallAfter(self.frame.on_stop, None)

    def on_pause(self, event):
        wx.CallAfter(self.frame.on_pause, None)

    def on_resume(self, event):
        wx.CallAfter(self.frame.on_resume, None)

    def on_switch_profile(self, profile_id):
        wx.CallAfter(self.frame.connect_profile, profile_id)

    def on_exit(self, event):
        self.frame.force_close()

class MainFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title=APP_NAME, size=(1200, 800))
        
        self.config_manager = ConfigManager()
        
        # Start Global Session (Background Local Mode)
        try:
            SessionManager.get_instance()
        except Exception as e:
            print(f"Failed to start local background session: {e}")

        self.client = None
        self.connected = False
        self.all_torrents = []
        self.current_filter = "All"
        self.current_profile_id = None
        self.client_generation = 0
        self.client_default_save_path = None
        self.known_hashes = set()
        self.pending_add_baseline = None
        self.pending_auto_start = False
        self.pending_auto_start_attempts = 0
        self.pending_hash_starts = set()
        self.thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.refreshing = False
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_timer, self.timer)
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.Bind(wx.EVT_ICONIZE, self.on_minimize)
        
        # Taskbar Icon
        self.tb_icon = TaskBarIcon(self)
        self.SetIcon(get_app_icon())
        
        # Menu Bar
        self._build_menu_bar()

        # Splitter Window
        self.splitter = wx.SplitterWindow(self)
        
        # Sidebar
        self.sidebar = wx.TreeCtrl(self.splitter, style=wx.TR_DEFAULT_STYLE | wx.TR_HIDE_ROOT | wx.TR_NO_LINES | wx.TR_FULL_ROW_HIGHLIGHT)
        self.sidebar.Bind(wx.EVT_TREE_SEL_CHANGED, self.on_filter_change)
        self.sidebar.SetName("Categories")
        self.root_id = self.sidebar.AddRoot("Root")
        self.cat_ids = {}
        self.cat_ids["All"] = self.sidebar.AppendItem(self.root_id, "All")
        self.cat_ids["Downloading"] = self.sidebar.AppendItem(self.root_id, "Downloading")
        self.cat_ids["Finished"] = self.sidebar.AppendItem(self.root_id, "Finished")
        self.cat_ids["Seeding"] = self.sidebar.AppendItem(self.root_id, "Seeding")
        self.cat_ids["Stopped"] = self.sidebar.AppendItem(self.root_id, "Stopped")
        self.cat_ids["Failed"] = self.sidebar.AppendItem(self.root_id, "Failed")
        self.trackers_root = self.sidebar.AppendItem(self.root_id, "Trackers")
        self.tracker_items = {} 
        self.sidebar.SelectItem(self.cat_ids["All"])
        self.sidebar.ExpandAll()

        # List
        self.torrent_list = TorrentListCtrl(self.splitter)
        self.torrent_list.Bind(wx.EVT_KEY_DOWN, self.on_list_key)
        self.torrent_list.Bind(wx.EVT_CONTEXT_MENU, self.on_context_menu)
        self.torrent_list.Bind(wx.EVT_RIGHT_DOWN, self.on_context_menu)
        
        self.splitter.SplitVertically(self.sidebar, self.torrent_list, 220)
        self.splitter.SetMinimumPaneSize(150)

        self.statusbar = self.CreateStatusBar(2)
        self.statusbar.SetStatusText("Disconnected", 0)

        
        self.Center()
        
        # Initialize preferred path
        self._update_client_default_save_path()

        # Attempt auto-connect
        wx.CallAfter(self.try_auto_connect)

    def show_from_tray(self):
        if not self.IsShown():
            self.Show()
        if self.IsIconized():
            self.Restore()
        self.Raise()

    def _build_menu_bar(self):
        """Build or rebuild the menu bar.

        The Connect entry is a submenu when profiles exist, enabling quick switching.
        """
        menubar = wx.MenuBar()

        # ----- File menu -----
        file_menu = wx.Menu()

        profiles = self.config_manager.get_profiles()
        self._connect_menu_id_to_profile = {}

        if profiles:
            connect_menu = wx.Menu()
            default_id = self.config_manager.get_default_profile_id()

            # Sort profiles by name for predictable navigation.
            def _sort_key(kv):
                pid, p = kv
                return str(p.get("name", pid)).lower()

            for pid, p in sorted(profiles.items(), key=_sort_key):
                label = str(p.get("name") or pid)
                if default_id and pid == default_id:
                    label += " (Default)"
                item = connect_menu.Append(wx.ID_ANY, label, "Connect to this profile")
                self._connect_menu_id_to_profile[item.GetId()] = pid
                self.Bind(wx.EVT_MENU, self.on_connect_profile_menu, item)

            # Put the Connection Manager entry at the bottom of the submenu,
            # after all existing profile choices.
            connect_menu.AppendSeparator()
            manage_item = connect_menu.Append(
                wx.ID_ANY,
                "Connection Manager...\tCtrl+Shift+C",
                "Add/edit/delete profiles and connect"
            )
            self.Bind(wx.EVT_MENU, self.on_connect, manage_item)

            file_menu.AppendSubMenu(connect_menu, "&Connect", "Connect or switch profile")
        else:
            connect_item = file_menu.Append(
                wx.ID_ANY,
                "&Connect...\tCtrl+Shift+C",
                "Manage Profiles & Connect"
            )
            self.Bind(wx.EVT_MENU, self.on_connect, connect_item)

        add_file_item = file_menu.Append(
            wx.ID_ANY,
            "Add Torrent &File...\tCtrl+O",
            "Add a torrent from a local file"
        )
        add_url_item = file_menu.Append(
            wx.ID_ANY,
            "Add &URL/Magnet...\tCtrl+U",
            "Add a torrent from a URL or Magnet link"
        )
        create_torrent_item = file_menu.Append(
            wx.ID_ANY,
            "Create &Torrent...\tCtrl+N",
            "Create a .torrent file from a file or folder"
        )
        file_menu.AppendSeparator()
        exit_item = file_menu.Append(wx.ID_EXIT, "E&xit", "Exit application")
        menubar.Append(file_menu, "&File")

        # ----- Actions menu -----
        actions_menu = wx.Menu()
        start_item = actions_menu.Append(wx.ID_ANY, "&Start\tCtrl+S", "Start selected torrents")
        pause_item = actions_menu.Append(wx.ID_ANY, "&Pause\tCtrl+P", "Pause selected torrents")
        resume_item = actions_menu.Append(wx.ID_ANY, "&Resume\tCtrl+R", "Resume selected torrents")
        actions_menu.AppendSeparator()
        recheck_item = actions_menu.Append(wx.ID_ANY, "Force &Recheck", "Force a recheck/verification (if supported)")
        reannounce_item = actions_menu.Append(wx.ID_ANY, "Force &Reannounce", "Force an immediate tracker announce (if supported)")
        actions_menu.AppendSeparator()
        copy_hash_item = actions_menu.Append(wx.ID_ANY, "Copy &Info Hash\tCtrl+I", "Copy the info hash for selected torrents")
        copy_magnet_item = actions_menu.Append(wx.ID_ANY, "Copy &Magnet Link\tCtrl+M", "Copy a magnet link for selected torrents")
        open_folder_item = actions_menu.Append(wx.ID_ANY, "Open Download &Folder", "Open the download folder (if available)")
        actions_menu.AppendSeparator()
        remove_item = actions_menu.Append(wx.ID_ANY, "&Remove\tDel", "Remove selected torrents")
        remove_data_item = actions_menu.Append(wx.ID_ANY, "Remove with &Data\tShift+Del", "Remove selected torrents and data")
        select_all_item = actions_menu.Append(wx.ID_SELECTALL, "Select &All\tCtrl+A", "Select all torrents")
        menubar.Append(actions_menu, "&Actions")

        # ----- Tools menu -----
        tools_menu = wx.Menu()
        prefs_item = tools_menu.Append(wx.ID_PREFERENCES, "&Preferences...\tCtrl+,", "Configure application settings")
        assoc_item = tools_menu.Append(wx.ID_ANY, "Register &Associations", "Associate .torrent and magnet links with this app")
        tools_menu.AppendSeparator()
        self.remote_prefs_item = tools_menu.Append(wx.ID_ANY, "qBittorrent Remote Preferences", "Edit connected qBittorrent settings")
        self.remote_prefs_item.Enable(False)
        menubar.Append(tools_menu, "T&ools")

        self.SetMenuBar(menubar)

        # Bind actions for the non-connect file menu items.
        self.Bind(wx.EVT_MENU, self.on_add_file, add_file_item)
        self.Bind(wx.EVT_MENU, self.on_add_url, add_url_item)
        self.Bind(wx.EVT_MENU, self.on_create_torrent, create_torrent_item)
        self.Bind(wx.EVT_MENU, self.on_prefs, prefs_item)
        self.Bind(wx.EVT_MENU, lambda e: self.Close(), exit_item)

        # Bind actions menu.
        self.Bind(wx.EVT_MENU, self.on_start, start_item)
        self.Bind(wx.EVT_MENU, self.on_pause, pause_item)
        self.Bind(wx.EVT_MENU, self.on_resume, resume_item)
        self.Bind(wx.EVT_MENU, self.on_recheck, recheck_item)
        self.Bind(wx.EVT_MENU, self.on_reannounce, reannounce_item)
        self.Bind(wx.EVT_MENU, self.on_copy_info_hash, copy_hash_item)
        self.Bind(wx.EVT_MENU, self.on_copy_magnet, copy_magnet_item)
        self.Bind(wx.EVT_MENU, self.on_open_download_folder, open_folder_item)
        self.Bind(wx.EVT_MENU, self.on_remove, remove_item)
        self.Bind(wx.EVT_MENU, self.on_remove_data, remove_data_item)
        self.Bind(wx.EVT_MENU, self.on_select_all, select_all_item)

        # Tools menu extras.
        self.Bind(wx.EVT_MENU, lambda e: register_associations(), assoc_item)
        self.Bind(wx.EVT_MENU, self.on_remote_preferences, self.remote_prefs_item)

        # Keep the remote-preferences menu in sync with connection state.
        self._update_remote_prefs_menu_state()
        # Accelerator table: ensure shortcuts work regardless of focus.
        accel_entries = [
            (wx.ACCEL_CTRL, ord('A'), select_all_item.GetId()),
            (wx.ACCEL_CTRL, ord('S'), start_item.GetId()),
            (wx.ACCEL_CTRL, ord('P'), pause_item.GetId()),
            (wx.ACCEL_CTRL, ord('R'), resume_item.GetId()),
            (wx.ACCEL_NORMAL, wx.WXK_DELETE, remove_item.GetId()),
            (wx.ACCEL_SHIFT, wx.WXK_DELETE, remove_data_item.GetId()),
            (wx.ACCEL_CTRL, ord('O'), add_file_item.GetId()),
            (wx.ACCEL_CTRL, ord('U'), add_url_item.GetId()),
            (wx.ACCEL_CTRL, ord('N'), create_torrent_item.GetId()),
            (wx.ACCEL_CTRL, ord('I'), copy_hash_item.GetId()),
            (wx.ACCEL_CTRL, ord('M'), copy_magnet_item.GetId()),
            (wx.ACCEL_CTRL, ord(','), prefs_item.GetId()),
        ]
        self.SetAcceleratorTable(wx.AcceleratorTable(accel_entries))


    def on_connect_profile_menu(self, event):
        pid = getattr(self, "_connect_menu_id_to_profile", {}).get(event.GetId())
        if not pid:
            return
        self.connect_profile(pid)


    def _update_client_default_save_path(self):
        prefs = self.config_manager.get_preferences()
        fallback = prefs.get('download_path', '')
        path = fallback
        if self.client:
            try:
                candidate = self.client.get_default_save_path()
                if candidate is not None:
                    path = candidate
            except Exception as e:
                pass
        self.client_default_save_path = path

    def _update_remote_prefs_menu_state(self):
        enabled = isinstance(self.client, QBittorrentClient) and self.connected
        if hasattr(self, "remote_prefs_item"):
            self.remote_prefs_item.Enable(enabled)

    def _prepare_auto_start(self):
        if not self.client:
            return

        self.pending_add_baseline = set(self.known_hashes)
        self.pending_auto_start = True
        self.pending_auto_start_attempts = 0
        self.pending_hash_starts = set()

    def _maybe_hash_from_torrent_bytes(self, data):
        if lt:
            try:
                info = lt.torrent_info(data)
                return str(info.info_hash())
            except Exception:
                return None
        return None

    def _maybe_hash_from_magnet(self, url):
        try:
            import urllib.parse
            parsed = urllib.parse.urlparse(url)
            qs = urllib.parse.parse_qs(parsed.query)
            xts = qs.get('xt', [])
            for xt in xts:
                if xt.startswith("urn:btih:"):
                    return xt.split(":")[-1].lower()
        except Exception:
            pass

        if lt:
            try:
                params = lt.parse_magnet_uri(url)
                if params.info_hashes.has_v1():
                    return str(params.info_hashes.v1)
            except Exception:
                pass
        return None

    def _auto_start_hashes(self, generation, hashes):
        try:
            import time
            time.sleep(0.3)
            for h in hashes:
                if generation != self.client_generation:
                    return
                if self.client:
                    self.client.start_torrent(h)
            wx.CallAfter(self.statusbar.SetStatusText, "Auto-started new torrent(s)", 0)
            wx.CallAfter(self.refresh_data)
        except Exception as e:
            wx.CallAfter(self.statusbar.SetStatusText, f"Auto-start failed: {e}", 0)

    def on_prefs(self, event):
        dlg = PreferencesDialog(self, self.config_manager)
        if dlg.ShowModal() == wx.ID_OK:
            prefs = dlg.get_preferences()
            self.config_manager.set_preferences(prefs)
            # Apply to session immediately
            try:
                SessionManager.get_instance().apply_preferences(prefs)
            except Exception as e:
                wx.LogError(f"Failed to apply settings: {e}")
            self._update_client_default_save_path()
        dlg.Destroy()

    def on_remote_preferences(self, event):
        if not self.connected or not isinstance(self.client, QBittorrentClient):
            wx.MessageBox("Remote preferences are only available when connected to qBittorrent.", "Information", wx.OK | wx.ICON_INFORMATION)
            return

        self.statusbar.SetStatusText("Fetching qBittorrent preferences...", 0)
        self.thread_pool.submit(self._fetch_remote_preferences)

    def _fetch_remote_preferences(self):
        try:
            prefs = self.client.get_app_preferences()
            wx.CallAfter(self._show_remote_preferences_dialog, prefs)
        except Exception as e:
            wx.CallAfter(wx.LogError, f"Failed to fetch remote preferences: {e}")

    def _show_remote_preferences_dialog(self, prefs):
        if not prefs:
            wx.MessageBox("Failed to retrieve preferences from qBittorrent.", "Error", wx.OK | wx.ICON_ERROR)
            return

        dlg = RemotePreferencesDialog(self, prefs)
        if dlg.ShowModal() == wx.ID_OK:
            try:
                parsed = dlg.GetPreferences()
                self.thread_pool.submit(self._apply_remote_preferences, parsed)
            except ValueError as e:
                wx.MessageBox(f"{e}", "Error", wx.OK | wx.ICON_ERROR)
        dlg.Destroy()

    def _apply_remote_preferences(self, prefs):
        try:
            self.client.set_app_preferences(prefs)
            wx.CallAfter(self.statusbar.SetStatusText, "qBittorrent preferences saved", 0)
            wx.CallAfter(self._update_client_default_save_path)
        except Exception as e:
            wx.CallAfter(wx.LogError, f"Failed to update remote preferences: {e}")

    def on_minimize(self, event):
        prefs = self.config_manager.get_preferences()
        if prefs.get('min_to_tray', True):
            self.Hide()
        else:
            event.Skip()

    def on_close(self, event):
        if event.CanVeto():
            prefs = self.config_manager.get_preferences()
            if prefs.get('close_to_tray', True):
                self.Hide()
                event.Veto()
                return

        self.force_close()

    def force_close(self):
        # Save local state
        self.tb_icon.RemoveIcon()
        self.tb_icon.Destroy()
        try:
            SessionManager.get_instance().save_state()
        except:
            pass
        self.Destroy()
        sys.exit(0)

    def connect_profile(self, pid):
        p = self.config_manager.get_profile(pid)
        if not p: return
        
        self.current_profile_id = pid
        self.client_default_save_path = None
        self.client_generation += 1

        # Reset state before connecting
        self.timer.Stop()
        self.connected = False
        self.client = None
        self.all_torrents = []
        self.torrent_list.update_data([])
        self.statusbar.SetStatusText("Connecting...", 0)
        self.known_hashes.clear()
        self.pending_add_baseline = None
        self.pending_auto_start = False
        self.pending_auto_start_attempts = 0
        self.pending_hash_starts = set()
        self._update_remote_prefs_menu_state()
        
        try:
            if p['type'] == 'local':
                self.client = LocalClient(p['url'])
            elif p['type'] == 'rtorrent':
                self.client = RTorrentClient(p['url'], p['user'], p['password'])
            elif p['type'] == 'qbittorrent':
                self.client = QBittorrentClient(p['url'], p['user'], p['password'])
            elif p['type'] == 'transmission':
                self.client = TransmissionClient(p['url'], p['user'], p['password'])
                
            self.connected = True
            self._update_client_default_save_path()
            
            status_msg = f"Connected to {p['name']}"
            if p['type'] != 'local':
                status_msg += " (Local session active)"
            
            self.statusbar.SetStatusText(status_msg, 0)
            self.refresh_data()
            self.timer.Start(2000) # Refresh every 2 seconds
            self._update_remote_prefs_menu_state()
        except Exception as e:
            wx.LogError(f"Connection failed: {e}")
            self.connected = False
            self.statusbar.SetStatusText("Connection Failed", 0)
            self._update_remote_prefs_menu_state()

    def on_connect(self, event):
        dlg = ConnectDialog(self, self.config_manager)
        if dlg.ShowModal() == wx.ID_OK:
            pid = dlg.selected_profile_id
            self.connect_profile(pid)
        dlg.Destroy()
        # Profiles may have been added/edited; rebuild the menu bar to reflect changes.
        self._build_menu_bar()

    def on_timer(self, event):
        if self.connected:
            self.refresh_data()

    def refresh_data(self):
        if not self.client or self.refreshing: return
        
        self.refreshing = True
        filter_mode = self.current_filter
        generation = self.client_generation
        self.thread_pool.submit(self._fetch_and_process_data, filter_mode, generation)

    def _fetch_and_process_data(self, filter_mode, generation):
        try:
            torrents = self.client.get_torrents_full()
            
            display_data = []
            stats = {"All": 0, "Downloading": 0, "Finished": 0, "Seeding": 0, "Stopped": 0, "Failed": 0}
            tracker_counts = {}
            
            for t in torrents:
                name = t.get('name', 'Unknown')
                size = self.fmt_size(t.get('size', 0))
                
                done = t.get('done', 0)
                total = t.get('size', 1)
                pct = 0
                if total > 0: pct = (done / total) * 100
                progress = f"{pct:.1f}%"
                
                uploaded = self.fmt_size(t.get('up_total', 0))
                
                ratio_val = t.get('ratio', 0)
                ratio = f"{ratio_val / 1000:.2f}"
                
                state = t.get('state', 0)
                active = t.get('active', 0)
                hashing = t.get('hashing', 0)
                msg = t.get('message', '')
                down_rate = t.get('down_rate', 0)
                up_rate = t.get('up_rate', 0)
                tracker_domain = t.get('tracker_domain', 'Unknown') or 'Unknown'
                
                status_str = "Stopped"
                if hashing:
                    status_str = "Checking"
                elif state == 1:
                    if pct >= 100:
                        status_str = "Seeding"
                        if up_rate > 0: status_str += f" {self.fmt_size(up_rate)}/s"
                    else:
                        status_str = "Downloading"
                        if down_rate > 0: status_str += f" {self.fmt_size(down_rate)}/s"
                
                if msg: status_str += f" ({msg})"

                t_hash = t.get('hash', '')
                
                is_seeding = (state == 1 and pct >= 100)
                is_stopped = (state == 0)
                is_error = (len(msg) > 0)
                
                stats["All"] += 1
                if state == 1 and pct < 100: stats["Downloading"] += 1
                if pct >= 100: stats["Finished"] += 1
                if is_seeding: stats["Seeding"] += 1
                if is_stopped: stats["Stopped"] += 1
                if is_error: stats["Failed"] += 1
                
                tracker_counts[tracker_domain] = tracker_counts.get(tracker_domain, 0) + 1
                    
                include = False
                if filter_mode == "All": include = True
                elif filter_mode == "Downloading" and state == 1 and pct < 100: include = True
                elif filter_mode == "Finished" and pct >= 100: include = True
                elif filter_mode == "Seeding" and is_seeding: include = True
                elif filter_mode == "Stopped" and is_stopped: include = True
                elif filter_mode == "Failed" and is_error: include = True
                elif filter_mode == tracker_domain: include = True
                
                if include:
                    display_data.append([name, size, progress, uploaded, ratio, status_str, t_hash])
            
            g_down, g_up = 0, 0
            try:
                g_down, g_up = self.client.get_global_stats()
            except: pass
            
            wx.CallAfter(self._on_refresh_complete, generation, torrents, display_data, stats, tracker_counts, g_down, g_up)
            
        except Exception as e:
            wx.CallAfter(self._on_refresh_error, generation, e)

    def _on_refresh_complete(self, generation, torrents, display_data, stats, tracker_counts, g_down, g_up):
        self.refreshing = False
        if not self.connected or generation != self.client_generation:
            return

        self.all_torrents = torrents
        self.torrent_list.update_data(display_data)
        current_hashes = {t.get('hash') for t in torrents if t.get('hash')}
        self.known_hashes = current_hashes
        
        for key, item_id in self.cat_ids.items():
            self.sidebar.SetItemText(item_id, f"{key} ({stats[key]})")
            
        # Update Trackers
        # 1. Update or Add
        for tracker, count in tracker_counts.items():
            label = f"{tracker} ({count})"
            if tracker in self.tracker_items:
                # Update existing
                item_id = self.tracker_items[tracker]
                if self.sidebar.GetItemText(item_id) != label:
                    self.sidebar.SetItemText(item_id, label)
            else:
                # Add new
                item_id = self.sidebar.AppendItem(self.trackers_root, label)
                self.tracker_items[tracker] = item_id
        
        # 2. Remove old (optional, but good for cleanup)
        to_remove = []
        for tracker, item_id in self.tracker_items.items():
            if tracker not in tracker_counts:
                self.sidebar.Delete(item_id)
                to_remove.append(tracker)
        for t in to_remove:
            del self.tracker_items[t]
            
        self.sidebar.Expand(self.trackers_root)

        self.statusbar.SetStatusText(f"DL: {self.fmt_size(g_down)}/s | UL: {self.fmt_size(g_up)}/s", 1)

        if self.pending_auto_start:
            target_hashes = set(current_hashes)
            if self.pending_hash_starts:
                target_hashes |= self.pending_hash_starts
            if self.pending_add_baseline is not None:
                target_hashes = target_hashes - self.pending_add_baseline

            if target_hashes:
                self.pending_auto_start = False
                self.pending_add_baseline = None
                self.pending_auto_start_attempts = 0
                self.pending_hash_starts.clear()
                self.thread_pool.submit(self._auto_start_hashes, generation, target_hashes)
            else:
                self.pending_auto_start_attempts += 1
                if self.pending_auto_start_attempts >= 5:
                    self.pending_auto_start = False
                    self.pending_add_baseline = None
                    self.pending_auto_start_attempts = 0
                    self.pending_hash_starts.clear()

    def _on_refresh_error(self, generation, e):
        self.refreshing = False
        if generation != self.client_generation:
            return
        print(f"Refresh error: {e}")

    def fmt_size(self, size):
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"

    def fetch_trackers(self):
        prefs = self.config_manager.get_preferences()
        if not prefs.get('enable_trackers', True):
            return []
        
        url = prefs.get('tracker_url', '')
        if not url: return []

        try:
            # Simple caching
            if hasattr(self, '_cached_trackers') and self._cached_trackers:
                return self._cached_trackers

            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                trackers = [line.strip() for line in r.text.splitlines() if line.strip()]
                self._cached_trackers = trackers
                return trackers
        except Exception as e:
            print(f"Failed to fetch trackers: {e}")
        return []

    def _get_default_save_path(self):
        if self.client_default_save_path is not None:
            return self.client_default_save_path
        return self.config_manager.get_preferences().get('download_path', '')

    def on_add_file(self, event):
        with wx.FileDialog(self, "Open Torrent File", wildcard="Torrent files (*.torrent)|*.torrent",
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as fileDialog:
            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return
            path = fileDialog.GetPath()
            try:
                with open(path, 'rb') as f:
                    data = f.read()
                
                # Parse torrent info for dialog
                file_list = []
                name = "Unknown"
                if lt:
                    try:
                        info = lt.torrent_info(data)
                        name = info.name()
                        num = info.num_files()
                        file_list = [(info.files().file_path(i), info.files().file_size(i)) for i in range(num)]
                    except Exception as e:
                        pass

                # Use the cached client default (remote path when connected, fallback to preferences)
                default_path = self._get_default_save_path()
                
                dlg = AddTorrentDialog(self, name, file_list, default_path)
                if dlg.ShowModal() == wx.ID_OK:
                    save_path = dlg.get_selected_path()
                    if not save_path:
                        save_path = None
                    priorities = dlg.get_file_priorities()
                    hash_hint = self._maybe_hash_from_torrent_bytes(data)
                    
                    if self.client:
                        self._prepare_auto_start()
                        if hash_hint:
                            self.pending_hash_starts.add(hash_hint)
                        self.client.add_torrent_file(data, save_path, priorities)
                        self.refresh_data()
                dlg.Destroy()

            except Exception as e:
                wx.LogError(f"Error adding file: {e}")

    def on_add_url(self, event):
        dlg = wx.TextEntryDialog(self, "Enter Magnet Link or URL:", "Add Torrent")
        if dlg.ShowModal() == wx.ID_OK:
            url = dlg.GetValue()
            if self.client:
                try:
                    # Use the cached client default (remote path when connected, fallback to preferences)
                    default_path = self._get_default_save_path()

                    if url.startswith("magnet:"):
                        # For magnets, we can't see files yet, but user can set path
                        adlg = AddTorrentDialog(self, "Magnet Link", None, default_path)
                        if adlg.ShowModal() == wx.ID_OK:
                            save_path = adlg.get_selected_path()
                            if not save_path:
                                save_path = None
                            hash_hint = self._maybe_hash_from_magnet(url)

                            trackers = self.fetch_trackers()
                            if trackers:
                                import urllib.parse
                                for t in trackers:
                                    url += f"&tr={urllib.parse.quote(t)}"

                            self._prepare_auto_start()
                            if hash_hint:
                                self.pending_hash_starts.add(hash_hint)
                            self.client.add_torrent_url(url, save_path)
                            self.refresh_data()
                        adlg.Destroy()

                    elif url.startswith(("http://", "https://")):
                        # Download .torrent file first
                        try:
                            r = requests.get(url, timeout=30)
                            r.raise_for_status()
                            data = r.content
                            
                            # Parse and show dialog (reuse on_add_file logic mostly)
                            file_list = []
                            name = "Unknown"
                            if lt:
                                try:
                                    info = lt.torrent_info(data)
                                    name = info.name()
                                    num = info.num_files()
                                    file_list = [(info.files().file_path(i), info.files().file_size(i)) for i in range(num)]
                                except: pass
                            
                            adlg = AddTorrentDialog(self, name, file_list, default_path)
                            if adlg.ShowModal() == wx.ID_OK:
                                save_path = adlg.get_selected_path()
                                if not save_path:
                                    save_path = None
                                priorities = adlg.get_file_priorities()
                                hash_hint = self._maybe_hash_from_torrent_bytes(data)
                                self._prepare_auto_start()
                                if hash_hint:
                                    self.pending_hash_starts.add(hash_hint)
                                self.client.add_torrent_file(data, save_path, priorities)
                                self.refresh_data()
                            adlg.Destroy()
                            
                        except Exception as e:
                            wx.LogError(f"Failed to download torrent from URL: {e}")

                except Exception as e:
                    wx.LogError(f"Error adding URL: {e}")
        dlg.Destroy()

    def _apply_to_selected(self, action, label):
        if not self.client or not action:
            if hasattr(self, "statusbar"):
                self.statusbar.SetStatusText("Not connected to any client.", 0)
            return

        hashes = self.torrent_list.get_selected_hashes()
        if not hashes:
            message = f"No torrents selected to {label.lower()}."
            if hasattr(self, "statusbar"):
                self.statusbar.SetStatusText(message, 0)
            else:
                print(message)
            return

        self.statusbar.SetStatusText(f"{label}ing torrents...", 0)
        self.thread_pool.submit(self._apply_background, action, hashes, label)

    def _apply_background(self, action, hashes, label):
        try:
            for h in hashes:
                action(h)
            wx.CallAfter(self._on_action_complete, f"{label} complete")
        except Exception as e:
            wx.CallAfter(self._on_action_error, f"Failed to {label.lower()} torrent: {e}")

    def on_start(self, event):
        action = self.client.start_torrent if self.client else None
        self._apply_to_selected(action, "Start")

    def on_stop(self, event):
        action = self.client.stop_torrent if self.client else None
        self._apply_to_selected(action, "Stop")

    def on_pause(self, event):
        action = self.client.stop_torrent if self.client else None
        self._apply_to_selected(action, "Pause")

    def on_resume(self, event):
        action = self.client.start_torrent if self.client else None
        self._apply_to_selected(action, "Resume")


    def on_recheck(self, event):
        if not self.client or not hasattr(self.client, "recheck_torrent"):
            self.statusbar.SetStatusText("Recheck not supported by this client.", 0)
            return
        try:
            # Probe support
            pass
        except Exception:
            pass
        self._apply_to_selected(self.client.recheck_torrent, "Recheck")

    def on_reannounce(self, event):
        if not self.client or not hasattr(self.client, "reannounce_torrent"):
            self.statusbar.SetStatusText("Reannounce not supported by this client.", 0)
            return
        self._apply_to_selected(self.client.reannounce_torrent, "Reannounce")

    def _set_clipboard_text(self, text: str) -> bool:
        try:
            if not wx.TheClipboard.Open():
                return False
            wx.TheClipboard.SetData(wx.TextDataObject(text))
            wx.TheClipboard.Close()
            return True
        except Exception:
            try:
                wx.TheClipboard.Close()
            except Exception:
                pass
            return False

    def _get_selected_torrent_objects(self):
        hashes = self.torrent_list.get_selected_hashes()
        if not hashes:
            return [], []
        tmap = {}
        for t in self.all_torrents:
            h = t.get("hash")
            if h:
                tmap[h] = t
        objs = []
        missing = []
        for h in hashes:
            t = tmap.get(h)
            if t:
                objs.append(t)
            else:
                missing.append(h)
        return objs, missing

    def on_copy_info_hash(self, event):
        objs, missing = self._get_selected_torrent_objects()
        hashes = [t.get("hash") for t in objs if t.get("hash")] + missing
        hashes = [h for h in hashes if h]
        if not hashes:
            self.statusbar.SetStatusText("No torrents selected.", 0)
            return
        text = "\n".join(hashes)
        if self._set_clipboard_text(text):
            self.statusbar.SetStatusText("Info hash copied to clipboard.", 0)
        else:
            self.statusbar.SetStatusText("Failed to access clipboard.", 0)

    def on_copy_magnet(self, event):
        objs, missing = self._get_selected_torrent_objects()
        hashes = [t.get("hash") for t in objs if t.get("hash")] + missing
        hashes = [h for h in hashes if h]
        if not hashes:
            self.statusbar.SetStatusText("No torrents selected.", 0)
            return

        magnets = []
        for h in hashes:
            magnets.append(f"magnet:?xt=urn:btih:{h}")

        text = "\n".join(magnets)
        if self._set_clipboard_text(text):
            self.statusbar.SetStatusText("Magnet link(s) copied to clipboard.", 0)
        else:
            self.statusbar.SetStatusText("Failed to access clipboard.", 0)

    def _open_path(self, path: str):
        if not path or not os.path.isdir(path):
            return False
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)  # type: ignore[attr-defined]
                return True
            if sys.platform == "darwin":
                subprocess.Popen(["open", path])
                return True
            subprocess.Popen(["xdg-open", path])
            return True
        except Exception:
            return False

    def on_open_download_folder(self, event):
        objs, missing = self._get_selected_torrent_objects()
        if not objs:
            self.statusbar.SetStatusText("No torrent selected.", 0)
            return
        # open the first selected torrent folder
        t = objs[0]
        path = t.get("save_path") or ""
        if not path:
            # fallback to client default save path
            path = self.client_default_save_path or ""
        if self._open_path(path):
            self.statusbar.SetStatusText("Opened download folder.", 0)
        else:
            self.statusbar.SetStatusText("Download folder not available.", 0)

    def on_create_torrent(self, event):
        dlg = CreateTorrentDialog(self)
        try:
            if dlg.ShowModal() != wx.ID_OK:
                dlg.Destroy()
                return
            try:
                opts = dlg.get_options()
            except Exception as e:
                dlg.Destroy()
                wx.MessageBox(str(e), "Create Torrent", wx.OK | wx.ICON_ERROR)
                return
            dlg.Destroy()
        except Exception:
            try:
                dlg.Destroy()
            except Exception:
                pass
            raise

        if not lt:
            wx.MessageBox("libtorrent is not available. Torrent creation requires python-libtorrent.", "Create Torrent", wx.OK | wx.ICON_ERROR)
            return

        source_path = opts["source_path"]
        output_path = opts["output_path"]

        progress = wx.ProgressDialog(
            "Create Torrent",
            "Hashing pieces and generating torrent metadata...",
            maximum=100,
            parent=self,
            style=wx.PD_APP_MODAL | wx.PD_PULSE | wx.PD_ELAPSED_TIME,
        )

        result = {"torrent_bytes": None, "magnet": "", "info_hash": "", "error": None}

        def worker():
            try:
                torrent_bytes, magnet, info_hash = create_torrent_bytes(
                    source_path=source_path,
                    trackers=opts.get("trackers", []),
                    web_seeds=opts.get("web_seeds", []),
                    piece_size=opts.get("piece_size", 0),
                    private=opts.get("private", False),
                    comment=opts.get("comment", ""),
                    creator=opts.get("creator", ""),
                    source=opts.get("source", ""),
                )
                # Write output
                out_dir = os.path.dirname(os.path.abspath(output_path))
                if out_dir and not os.path.isdir(out_dir):
                    os.makedirs(out_dir, exist_ok=True)
                with open(output_path, "wb") as f:
                    f.write(torrent_bytes)
                result["torrent_bytes"] = torrent_bytes
                result["magnet"] = magnet
                result["info_hash"] = info_hash
            except Exception as e:
                result["error"] = str(e)

        th = threading.Thread(target=worker, daemon=True)
        th.start()

        def poll():
            if th.is_alive():
                try:
                    progress.Pulse()
                except Exception:
                    pass
                wx.CallLater(200, poll)
                return
            try:
                progress.Destroy()
            except Exception:
                pass

            if result["error"]:
                wx.MessageBox(result["error"], "Create Torrent", wx.OK | wx.ICON_ERROR)
                return

            # Optional clipboard copy
            if opts.get("copy_magnet") and result.get("magnet"):
                self._set_clipboard_text(result["magnet"])

            # Optional add to client
            if opts.get("add_to_client") and self.client:
                try:
                    # Add torrent file content; prompt for save path via existing dialog
                    with open(output_path, "rb") as f:
                        content = f.read()
                    self._prepare_auto_start()
                    self.client.add_torrent_file(content)
                    self.refresh_data()
                except Exception as e:
                    wx.MessageBox(f"Created torrent, but failed to add to client: {e}", "Create Torrent", wx.OK | wx.ICON_WARNING)

            msg = f"Torrent created:\n{output_path}"
            if result.get("info_hash"):
                msg += f"\nInfo Hash: {result['info_hash']}"
            if result.get("magnet"):
                msg += f"\nMagnet copied to clipboard." if opts.get("copy_magnet") else f"\nMagnet: {result['magnet']}"
            wx.MessageBox(msg, "Create Torrent", wx.OK | wx.ICON_INFORMATION)

        wx.CallLater(200, poll)

    def on_remove(self, event):
        hashes = self.torrent_list.get_selected_hashes()
        if hashes and wx.MessageBox(f"Remove {len(hashes)} torrents?", "Confirm", wx.YES_NO) == wx.YES:
            self.statusbar.SetStatusText("Removing torrents...", 0)
            self.thread_pool.submit(self._remove_background, hashes, False)
            
    def on_remove_data(self, event):
        hashes = self.torrent_list.get_selected_hashes()
        if not hashes:
            return
        count = len(hashes)
        label = 'torrent' if count == 1 else 'torrents'
        if wx.MessageBox(f"Remove {count} {label} AND DATA?", "Confirm", wx.YES_NO | wx.ICON_WARNING) != wx.YES:
            return
        self.statusbar.SetStatusText("Removing torrents and data...", 0)
        self.thread_pool.submit(self._remove_background, hashes, True)

    def _remove_background(self, hashes, with_data):
        try:
            if hasattr(self.client, 'remove_torrents'):
                self.client.remove_torrents(hashes, delete_files=with_data)
            else:
                for h in hashes:
                    if with_data:
                        self.client.remove_torrent_with_data(h)
                    else:
                        self.client.remove_torrent(h)
                    self.client.remove_torrent(h)
            wx.CallAfter(self._on_action_complete, "Removed torrents")
        except Exception as e:
            wx.CallAfter(self._on_action_error, f"Remove failed: {e}")

    def _on_action_complete(self, msg):
        self.statusbar.SetStatusText(msg, 0)
        self.refresh_data()

    def _on_action_error(self, msg):
         wx.MessageBox(msg, "Error", wx.OK | wx.ICON_ERROR)
         self.statusbar.SetStatusText("Error occurred", 0)

    def on_select_all(self, event):
        count = self.torrent_list.GetItemCount()
        for i in range(count):
            self.torrent_list.Select(i)

    def on_filter_change(self, event):
        item = event.GetItem()
        if item:
            text = self.sidebar.GetItemText(item)
            if "(" in text:
                text = text.rsplit(" (", 1)[0]
            self.current_filter = text
            self.refresh_data()

    def on_list_key(self, event):
        code = event.GetKeyCode()
        event.Skip()

    def on_context_menu(self, event):
        menu = wx.Menu()

        start = menu.Append(wx.ID_ANY, "Start")
        pause = menu.Append(wx.ID_ANY, "Pause")
        resume = menu.Append(wx.ID_ANY, "Resume")

        menu.AppendSeparator()
        recheck = menu.Append(wx.ID_ANY, "Force Recheck")
        reannounce = menu.Append(wx.ID_ANY, "Force Reannounce")

        menu.AppendSeparator()
        copy_hash = menu.Append(wx.ID_ANY, "Copy Info Hash")
        copy_magnet = menu.Append(wx.ID_ANY, "Copy Magnet Link")
        open_folder = menu.Append(wx.ID_ANY, "Open Download Folder")

        menu.AppendSeparator()
        remove = menu.Append(wx.ID_ANY, "Remove")
        remove_data = menu.Append(wx.ID_ANY, "Remove with Data")

        self.Bind(wx.EVT_MENU, self.on_start, start)
        self.Bind(wx.EVT_MENU, self.on_pause, pause)
        self.Bind(wx.EVT_MENU, self.on_resume, resume)
        self.Bind(wx.EVT_MENU, self.on_recheck, recheck)
        self.Bind(wx.EVT_MENU, self.on_reannounce, reannounce)
        self.Bind(wx.EVT_MENU, self.on_copy_info_hash, copy_hash)
        self.Bind(wx.EVT_MENU, self.on_copy_magnet, copy_magnet)
        self.Bind(wx.EVT_MENU, self.on_open_download_folder, open_folder)
        self.Bind(wx.EVT_MENU, self.on_remove, remove)
        self.Bind(wx.EVT_MENU, self.on_remove_data, remove_data)

        self.PopupMenu(menu)
        menu.Destroy()

    def try_auto_connect(self):
        default_id = self.config_manager.get_default_profile_id()
        if default_id:
             self.connect_profile(default_id)
        
        # Check for CLI args
        if len(sys.argv) > 1:
            arg = sys.argv[1]
            # If not connected, we force a connection dialog if no default was successful
            if not self.connected:
                self.on_connect(None)
            
            if self.connected:
                # Give it a moment or just proceed?
                # Add the torrent
                if arg.startswith("magnet:"):
                    try:
                        trackers = self.fetch_trackers()
                        if trackers:
                            import urllib.parse
                            for t in trackers:
                                arg += f"&tr={urllib.parse.quote(t)}"
                        
                        self._prepare_auto_start()
                        hash_hint = self._maybe_hash_from_magnet(arg)
                        if hash_hint:
                            self.pending_hash_starts.add(hash_hint)
                        self.client.add_torrent_url(arg)
                        self.statusbar.SetStatusText("Magnet link added from CLI", 0)
                        self.refresh_data()
                    except Exception as e:
                        wx.LogError(f"Failed to add magnet: {e}")
                elif os.path.exists(arg):
                    try:
                        with open(arg, 'rb') as f:
                            content = f.read()
                        hash_hint = self._maybe_hash_from_torrent_bytes(content)
                        self._prepare_auto_start()
                        if hash_hint:
                            self.pending_hash_starts.add(hash_hint)
                        self.client.add_torrent_file(content)
                        self.statusbar.SetStatusText("Torrent file added from CLI", 0)
                        self.refresh_data()
                    except Exception as e:
                        wx.LogError(f"Failed to add torrent file: {e}")
                else:
                    wx.LogError(f"Invalid argument: {arg}")

        if not self.connected and not default_id:
            self.on_connect(None)

if __name__ == "__main__":
    try:
        print("Starting application...")
        app = wx.App(False) # False = don't redirect stdout/stderr to window
        print("wx.App initialized.")
        frame = MainFrame()
        print("MainFrame initialized.")
        frame.Show()
        print("MainFrame shown. Entering MainLoop.")
        app.MainLoop()
        print("MainLoop exited.")
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        input("Press Enter to exit...")
