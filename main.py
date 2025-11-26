import wx
import sys
import os

from libtorrent_env import prepare_libtorrent_dlls

prepare_libtorrent_dlls()

import wx.adv
import threading
import json
import requests # Added for downloading torrent files from URL

from clients import RTorrentClient, QBittorrentClient, TransmissionClient, LocalClient
from config_manager import ConfigManager
from session_manager import SessionManager


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
        
        # URL / Path
        self.url_label = wx.StaticText(self, label="URL (e.g. scgi://... or http://...):")
        sizer.Add(self.url_label, 0, wx.ALL, 5)
        self.url_input = wx.TextCtrl(self, value=profile['url'] if profile else "")
        sizer.Add(self.url_input, 0, wx.EXPAND | wx.ALL, 5)
        
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
            self.user_input.Disable()
            self.pass_input.Disable()
        else:
            self.url_label.SetLabel("URL (e.g. scgi://... or http://...):")
            self.user_input.Enable()
            self.pass_input.Enable()

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
        
        sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        
        self.SetSizer(sizer)
        self.Center()
        
        self.selected_profile_id = None
        self.refresh_list()

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
            "enable_trackers": self.track_chk.GetValue(),
            "tracker_url": self.track_url_input.GetValue()
        }

class TaskBarIcon(wx.adv.TaskBarIcon):
    def __init__(self, frame):
        super().__init__()
        self.frame = frame
        self.SetIcon(get_app_icon(), APP_NAME)
        self.Bind(wx.adv.EVT_TASKBAR_LEFT_DCLICK, self.on_double_click)

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
        self.Bind(wx.EVT_MENU, self.on_stop, stop_item)
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
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_timer, self.timer)
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.Bind(wx.EVT_ICONIZE, self.on_minimize)
        
        # Taskbar Icon
        self.tb_icon = TaskBarIcon(self)
        self.SetIcon(get_app_icon())
        
        # Menu Bar
        menubar = wx.MenuBar()
        file_menu = wx.Menu()
        connect_item = file_menu.Append(wx.ID_ANY, "&Connect...\tCtrl+Shift+C", "Manage Profiles & Connect")
        add_file_item = file_menu.Append(wx.ID_ANY, "Add Torrent &File...\tCtrl+O", "Add a torrent from a local file")
        add_url_item = file_menu.Append(wx.ID_ANY, "Add &URL/Magnet...\tCtrl+U", "Add a torrent from a URL or Magnet link")
        file_menu.AppendSeparator()
        prefs_item = file_menu.Append(wx.ID_PREFERENCES, "&Preferences...\tCtrl+P", "Configure application settings")
        file_menu.AppendSeparator()
        exit_item = file_menu.Append(wx.ID_EXIT, "E&xit", "Exit application")
        menubar.Append(file_menu, "&File")
        
        torrent_menu = wx.Menu()
        start_item = torrent_menu.Append(wx.ID_ANY, "&Start\tCtrl+S", "Start selected torrents")
        stop_item = torrent_menu.Append(wx.ID_ANY, "Sto&p\tCtrl+P", "Stop selected torrents")
        remove_item = torrent_menu.Append(wx.ID_ANY, "&Remove\tDel", "Remove selected torrents")
        remove_data_item = torrent_menu.Append(wx.ID_ANY, "Remove with &Data\tShift+Del", "Remove selected torrents and data")
        select_all_item = torrent_menu.Append(wx.ID_SELECTALL, "Select &All\tCtrl+A", "Select all torrents")
        menubar.Append(torrent_menu, "&Torrent")
        
        tools_menu = wx.Menu()
        assoc_item = tools_menu.Append(wx.ID_ANY, "Register &Associations", "Associate .torrent and magnet links with this app")
        menubar.Append(tools_menu, "T&ools")

        self.SetMenuBar(menubar)
        
        # Event Bindings
        self.Bind(wx.EVT_MENU, self.on_connect, connect_item)
        self.Bind(wx.EVT_MENU, self.on_add_file, add_file_item)
        self.Bind(wx.EVT_MENU, self.on_add_url, add_url_item)
        self.Bind(wx.EVT_MENU, self.on_prefs, prefs_item)
        self.Bind(wx.EVT_MENU, lambda e: self.Close(), exit_item)
        self.Bind(wx.EVT_MENU, self.on_start, start_item)
        self.Bind(wx.EVT_MENU, self.on_stop, stop_item)
        self.Bind(wx.EVT_MENU, self.on_remove, remove_item)
        self.Bind(wx.EVT_MENU, self.on_remove_data, remove_data_item)
        self.Bind(wx.EVT_MENU, self.on_select_all, select_all_item)
        self.Bind(wx.EVT_MENU, lambda e: register_associations(), assoc_item)

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
        self.cat_ids["Complete"] = self.sidebar.AppendItem(self.root_id, "Complete")
        self.cat_ids["Active"] = self.sidebar.AppendItem(self.root_id, "Active")
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

        accel_entries = [
            (wx.ACCEL_CTRL, ord('A'), select_all_item.GetId()),
            (wx.ACCEL_CTRL, ord('S'), start_item.GetId()),
            (wx.ACCEL_CTRL, ord('P'), stop_item.GetId()),
            (wx.ACCEL_NORMAL, wx.WXK_DELETE, remove_item.GetId()),
            (wx.ACCEL_SHIFT, wx.WXK_DELETE, remove_data_item.GetId()),
            (wx.ACCEL_CTRL, ord('O'), add_file_item.GetId()),
            (wx.ACCEL_CTRL, ord('U'), add_url_item.GetId()),
        ]
        self.SetAcceleratorTable(wx.AcceleratorTable(accel_entries))
        
        self.Center()
        
        # Attempt auto-connect
        wx.CallAfter(self.try_auto_connect)

    def show_from_tray(self):
        if not self.IsShown():
            self.Show()
        if self.IsIconized():
            self.Restore()
        self.Raise()

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
        dlg.Destroy()

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
        
        # Reset state before connecting
        self.timer.Stop()
        self.connected = False
        self.client = None
        self.all_torrents = []
        self.torrent_list.update_data([])
        self.statusbar.SetStatusText("Connecting...", 0)
        
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
            
            status_msg = f"Connected to {p['name']}"
            if p['type'] != 'local':
                status_msg += " (Local session active)"
            
            self.statusbar.SetStatusText(status_msg, 0)
            self.refresh_data()
            self.timer.Start(2000) # Refresh every 2 seconds
        except Exception as e:
            wx.LogError(f"Connection failed: {e}")
            self.connected = False
            self.statusbar.SetStatusText("Connection Failed", 0)

    def on_connect(self, event):
        dlg = ConnectDialog(self, self.config_manager)
        if dlg.ShowModal() == wx.ID_OK:
            pid = dlg.selected_profile_id
            self.connect_profile(pid)
        dlg.Destroy()

    def on_timer(self, event):
        if self.connected:
            self.refresh_data()

    def refresh_data(self):
        if not self.client: return
        
        try:
            torrents = self.client.get_torrents_full()
            self.all_torrents = torrents
            
            display_data = []
            stats = {"All": 0, "Downloading": 0, "Complete": 0, "Active": 0}
            
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
                
                stats["All"] += 1
                if state == 1 and pct < 100: stats["Downloading"] += 1
                if pct >= 100: stats["Complete"] += 1
                if active == 1: stats["Active"] += 1
                    
                include = False
                if self.current_filter == "All": include = True
                elif self.current_filter == "Downloading" and state == 1 and pct < 100: include = True
                elif self.current_filter == "Complete" and pct >= 100: include = True
                elif self.current_filter == "Active" and active == 1: include = True
                
                if include:
                    display_data.append([name, size, progress, uploaded, ratio, status_str, t_hash])
            
            self.torrent_list.update_data(display_data)
            
            for key, item_id in self.cat_ids.items():
                self.sidebar.SetItemText(item_id, f"{key} ({stats[key]})")
                
            try:
                g_down, g_up = self.client.get_global_stats()
                if self.connected:
                    self.statusbar.SetStatusText(f"DL: {self.fmt_size(g_down)}/s | UL: {self.fmt_size(g_up)}/s", 1)
            except: pass

        except Exception as e:
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

    def on_add_file(self, event):
        with wx.FileDialog(self, "Open Torrent File", wildcard="Torrent files (*.torrent)|*.torrent",
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as fileDialog:
            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return
            path = fileDialog.GetPath()
            try:
                with open(path, 'rb') as f:
                    data = f.read()
                if self.client:
                    self.client.add_torrent_file(data)
                    self.refresh_data()
            except Exception as e:
                wx.LogError(f"Error adding file: {e}")

    def on_add_url(self, event):
        dlg = wx.TextEntryDialog(self, "Enter Magnet Link or URL:", "Add Torrent")
        if dlg.ShowModal() == wx.ID_OK:
            url = dlg.GetValue()
            if self.client:
                try:
                    if url.startswith("magnet:"):
                        trackers = self.fetch_trackers()
                        if trackers:
                            import urllib.parse
                            for t in trackers:
                                url += f"&tr={urllib.parse.quote(t)}"
                    
                    self.client.add_torrent_url(url)
                    self.refresh_data()
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

        for h in hashes:
            try:
                action(h)
            except Exception as e:
                wx.LogError(f"Failed to {label.lower()} torrent: {e}")
        self.refresh_data()

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

    def on_remove(self, event):
        hashes = self.torrent_list.get_selected_hashes()
        if hashes and wx.MessageBox(f"Remove {len(hashes)} torrents?", "Confirm", wx.YES_NO) == wx.YES:
            for h in hashes:
                self.client.remove_torrent(h)
            self.refresh_data()
            
    def on_remove_data(self, event):
        hashes = self.torrent_list.get_selected_hashes()
        if hashes and wx.MessageBox(f"Remove {len(hashes)} torrents AND DATA?", "Confirm", wx.YES_NO | wx.ICON_WARNING) == wx.YES:
            for h in hashes:
                self.client.remove_torrent_with_data(h)
            self.refresh_data()

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
        stop = menu.Append(wx.ID_ANY, "Stop")
        remove = menu.Append(wx.ID_ANY, "Remove")
        
        self.Bind(wx.EVT_MENU, self.on_start, start)
        self.Bind(wx.EVT_MENU, self.on_stop, stop)
        self.Bind(wx.EVT_MENU, self.on_remove, remove)
        
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
                                
                        self.client.add_torrent_url(arg)
                        self.statusbar.SetStatusText("Magnet link added from CLI", 0)
                        self.refresh_data()
                    except Exception as e:
                        wx.LogError(f"Failed to add magnet: {e}")
                elif os.path.exists(arg):
                    try:
                        with open(arg, 'rb') as f:
                            content = f.read()
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
