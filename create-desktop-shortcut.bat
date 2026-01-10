@echo off
echo Creating OpenCue desktop shortcut...

set SCRIPT="%TEMP%\create_shortcut.vbs"

echo Set oWS = WScript.CreateObject("WScript.Shell") > %SCRIPT%
echo sLinkFile = oWS.SpecialFolders("Desktop") ^& "\OpenCue.lnk" >> %SCRIPT%
echo Set oLink = oWS.CreateShortcut(sLinkFile) >> %SCRIPT%
echo oLink.TargetPath = "D:\opencue\start-opencue.bat" >> %SCRIPT%
echo oLink.WorkingDirectory = "D:\opencue" >> %SCRIPT%
echo oLink.Description = "Start OpenCue Backend" >> %SCRIPT%
echo oLink.Save >> %SCRIPT%

cscript /nologo %SCRIPT%
del %SCRIPT%

echo.
echo Done! OpenCue shortcut created on your desktop.
echo Double-click it to start the backend.
pause
