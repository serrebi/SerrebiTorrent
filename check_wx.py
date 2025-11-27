import wx
import wx.dataview

app = wx.App()
try:
    print(f"wx.dataview.TreeListCtrl exists: {hasattr(wx.dataview, 'TreeListCtrl')}")
except:
    print("wx.dataview.TreeListCtrl does not exist")

try:
    print(f"wx.TR_HAS_CHECKBOX exists: {hasattr(wx, 'TR_HAS_CHECKBOX')}")
except:
    print("wx.TR_HAS_CHECKBOX does not exist")
