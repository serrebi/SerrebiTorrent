import wx
import wx.dataview as dv

app = wx.App()
print("Checking wx.dataview attributes:")
for x in dir(dv):
    if "TL_" in x:
        print(x)
