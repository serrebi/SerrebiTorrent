import wx
app = wx.App()
print("wx attributes:")
for x in dir(wx):
    if x.startswith("TR_"):
        print(x)
print(f"TreeCtrl exists: {hasattr(wx, 'TreeCtrl')}")
