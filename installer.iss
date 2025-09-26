[Setup]
AppName=PowerSupplyGUI
AppVersion=1.0
DefaultDirName={pf}\PowerSupplyGUI
DefaultGroupName=PowerSupplyGUI
OutputBaseFilename=PowerSupplyInstaller
Compression=lzma
SolidCompression=yes

[Files]
Source: "C:\Users\SheydaAlavi\Desktop\pyplc\dist\main.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\PowerSupplyGUI"; Filename: "{app}\main.exe"
Name: "{commondesktop}\PowerSupplyGUI"; Filename: "{app}\main.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"; Flags: unchecked
