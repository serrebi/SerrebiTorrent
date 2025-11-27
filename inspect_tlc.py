import wx
import wx.dataview as dv

app = wx.App()
frame = wx.Frame(None)
tlc = dv.TreeListCtrl(frame)
print("TreeListCtrl attributes:")
for x in dir(tlc):
    if "Expand" in x:
        print(x)