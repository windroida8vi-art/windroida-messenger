@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist windroida.jks (
  echo windroida.jks already exists. Do NOT replace it: a new key means phones must uninstall the app first.
  pause
  exit /b 1
)
where keytool >nul 2>nul
if errorlevel 1 (
  echo keytool not found. It comes with Java / Android Studio ^(Android Studio\jbr\bin^). Add that folder to PATH and run again.
  pause
  exit /b 1
)
echo.
echo   This makes your permanent APK signing key: windroida.jks
echo   Choose a password and WRITE IT DOWN. Keep a backup copy of windroida.jks somewhere safe;
echo   if it is lost you can never update the app in place (everyone must uninstall + reinstall).
echo.
keytool -genkeypair -v -keystore windroida.jks -alias windroida -keyalg RSA -keysize 4096 -validity 36500 -dname "CN=Windroida, O=Windroida, C=IR"
if errorlevel 1 ( pause & exit /b 1 )
if not exist keystore.properties copy keystore.properties.example keystore.properties >nul
echo.
echo   Done. Now open keystore.properties and put the password you just chose in BOTH password lines.
echo   Then build the release APK:   gradle assembleRelease      ^(or Build ^> Generate Signed App Bundle / APK^)
echo   File:  app\build\outputs\apk\release\app-release.apk
pause
