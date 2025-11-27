import wx
import wx.lib.agw.customtreectrl as CT

print("CT attributes:")
for x in dir(CT):
    if "TR_" in x:
        print(x)
