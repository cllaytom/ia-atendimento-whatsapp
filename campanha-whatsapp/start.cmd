@echo off
setlocal
rem Atalho do worker da campanha sem depender da ExecutionPolicy do PowerShell.
rem
rem   start.cmd              -> simulacao
rem   start.cmd --manual     -> espera o botao "Enviar agora" do painel
rem   start.cmd --enviar     -> envio real automatico
rem   start.cmd --parear     -> vincular aparelho (QR)
rem   start.cmd --estado     -> ver estado do conector

set "WORKER=%~dp0worker.cjs"
if not exist "%WORKER%" (
  echo worker.cjs nao encontrado em %~dp0
  exit /b 1
)

set "NODE="
for %%C in (node.exe) do if not defined NODE set "NODE=%%~$PATH:C"

if not defined NODE (
  for /f "delims=" %%D in ('dir /b /ad /o-n "%APPDATA%\fnm\node-versions" 2^>nul') do (
    if not defined NODE if exist "%APPDATA%\fnm\node-versions\%%D\installation\node.exe" (
      set "NODE=%APPDATA%\fnm\node-versions\%%D\installation\node.exe"
    )
  )
)

if not defined NODE (
  echo Node.js nao encontrado.
  echo Instale com: winget install OpenJS.NodeJS.LTS
  exit /b 1
)

echo node: %NODE%
"%NODE%" "%WORKER%" %*
exit /b %ERRORLEVEL%
